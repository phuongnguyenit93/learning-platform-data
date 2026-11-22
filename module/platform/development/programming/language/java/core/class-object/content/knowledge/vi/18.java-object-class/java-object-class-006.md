# Hợp đồng `equals()` và mối liên hệ với `hashCode()` trong Java

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt **đồng nhất đối tượng** (*identity*) với **bằng nhau theo giá trị/ngữ nghĩa** (*logical equality*).
- Giải thích cách `Object.equals(Object)` và `Object.hashCode()` hoạt động theo mặc định, khi nào nên override và vì sao thường phải override **cả hai**.
- Thuộc và áp dụng năm yêu cầu cơ bản của hợp đồng `equals()`: **phản xạ**, **đối xứng**, **bắc cầu**, **nhất quán**, và **không bằng `null`**.
- Nắm quy tắc bắt buộc của `hashCode()`: **hai objects bằng nhau theo `equals` phải có hash code bằng nhau**, và hiểu chiều ngược lại **không đúng**.
- Thiết kế một immutable value object với `equals` và `hashCode` đúng, dùng `Objects.equals`/`Objects.hash` hoặc phép tính hash trực tiếp.
- Phân tích hành vi của `HashSet`, `HashMap`, `LinkedHashMap` và lý do key đổi trạng thái sau khi thêm vào hash collection gây lỗi tra cứu.
- Nhận diện lỗi **chỉ override `equals`**, hash code dựa vào field khác, không xử lý null, so sánh field bằng `==`, vi phạm đối xứng khi kế thừa.
- Phân biệt `getClass()` và `instanceof` khi xây `equals`, cân nhắc `final` class, sealed hierarchy và các vấn đề kế thừa/mở rộng.
- So sánh bình đẳng của primitive values, reference fields, arrays, nested arrays, `BigDecimal`, records và enums; không đánh đồng `compareTo()==0` với `equals()`.
- Viết kiểm thử deterministic cho tính phản xạ/đối xứng/bắc cầu/hash consistency mà không giả định giá trị cụ thể của `hashCode()` hoặc thứ tự duyệt `HashMap`.
- Sử dụng kiến thức này khi tạo keys, cache, sets, domain value objects và các API có hợp đồng equality rõ ràng trong Java 17+.

## 1. Ba câu hỏi không giống nhau

Xét:

~~~java
String first = new String("Java");
String second = new String("Java");
String alias = first;
~~~

Các câu hỏi:

1. **`first == second`?** Không. Hai references trỏ tới hai `String` objects riêng (đã dùng `new` hai lần).
2. **`first.equals(second)`?** Có. `String` định nghĩa equality dựa trên chuỗi ký tự.
3. **`first == alias`?** Có. Hai biến cùng trỏ một object.

Dùng `==` giữa **references** chủ yếu để so **identity**. Dùng `equals` khi muốn áp dụng **hợp đồng equality mà class công bố**.

Ví dụ một `Customer` có `customerId`: hai objects riêng có cùng ID có được coi là cùng khách hàng không? Tùy quyết định domain. Java không tự biết rằng ID là tiêu chí equality. Bạn phải chọn contract, triển khai đúng và giữ nó nhất quán.

### 1.1. `equals` khác `==` đối với primitives

Với `int a = 7; int b = 7;`, `a == b` so giá trị primitive và trả true. Primitives không có instance method `equals`.

Với `Integer x`/`Integer y` là references, `x == y` so object identity, trong khi `x.equals(y)` so numeric value theo hợp đồng của Integer. **Không dựa vào kết quả `Integer == Integer` để suy luận equality giá trị**, vì caching/boxing có thể làm identity khác nhau.

### 1.2. Không phải mọi `equals` đều so mọi field

Một value object `Money(amount, currency)` có thể xét cả amount và currency. Một entity `Order(id, status)` có thể định nghĩa equality theo stable ID mà bỏ status thay đổi. Một DTO có thể muốn equality theo mọi data fields.

**Tiêu chí equality là quyết định của API/domain**; không có công thức “luôn lấy tất cả fields” áp dụng cho mọi class.

## 2. `Object.equals` và `Object.hashCode` mặc định

Mọi class bình thường trực tiếp/gián tiếp kế thừa từ `java.lang.Object`. Nếu không override:

- `Object.equals(Object)` sử dụng **identity equality**: object chỉ bằng chính nó.
- `Object.hashCode()` trả một giá trị `int` thích hợp cho hợp đồng hash của Object; **không được coi là địa chỉ bộ nhớ** hoặc ID duy nhất tuyệt đối.
- `hashCode()` không bảo đảm mọi objects khác nhau có giá trị khác nhau.
- Hash code không phải key bảo mật, chữ ký số, ID bền vững hoặc cách xác nhận hai objects là một.

### 2.1. Demo mặc định

Lưu **`ObjectIdentityDemo.java`**:

~~~java
public class ObjectIdentityDemo {
    static final class Box {
        private final int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box first = new Box(7);
        Box second = new Box(7);
        Box alias = first;

        System.out.println("first==second=" + (first == second));
        System.out.println("first.equals(second)=" +
                first.equals(second));
        System.out.println("first==alias=" + (first == alias));
        System.out.println("first.equals(alias)=" +
                first.equals(alias));
    }
}
~~~

Biên dịch/chạy Java 17+:

~~~bash
javac ObjectIdentityDemo.java
java ObjectIdentityDemo
~~~

**Stdout:**

~~~text
first==second=false
first.equals(second)=false
first==alias=true
first.equals(alias)=true
~~~

Mặc dù hai Box objects có cùng `value = 7`, class `Box` chưa override `equals`, nên kết quả vẫn theo **identity**.

**Không in `first.hashCode()` rồi tuyên bố output phải là một số cụ thể.** Giá trị hash mặc định không cố định giữa các JVM/runs. Chương trình ở đây cố ý chỉ in những kết quả Java bảo đảm.

## 3. Hợp đồng chính thức của `equals(Object)`

Với những references **khác `null`**, hợp đồng của `Object.equals` nêu năm tính chất.

### 3.1. Tính phản xạ (*reflexive*)

Với mọi object `x` không null:

~~~java
x.equals(x) == true
~~~

Nếu object không bằng chính nó, nhiều collections và thuật toán sẽ không còn hợp lý.

### 3.2. Tính đối xứng (*symmetric*)

Với mọi `x`, `y` không null:

~~~java
x.equals(y) == y.equals(x)
~~~

Nếu `x` công nhận `y` bằng mình, `y` cũng phải công nhận `x` bằng nó. Đây là lỗi rất dễ gặp khi superclass dùng `instanceof` còn subclass thêm field riêng vào `equals`.

### 3.3. Tính bắc cầu (*transitive*)

Với mọi `x`, `y`, `z` không null:

~~~java
if (x.equals(y) && y.equals(z)) {
    // x.equals(z) cũng phải true.
}
~~~

Ví dụ nếu hai địa chỉ A và B được xem là bằng nhau, B và C bằng nhau, thì A và C cũng phải bằng nhau. Một kiểu equality có “ngưỡng sai số” dễ vi phạm tính bắc cầu.

### 3.4. Tính nhất quán (*consistent*)

Nhiều lần gọi `x.equals(y)` phải trả cùng kết quả **nếu những thông tin được sử dụng trong phép so sánh không thay đổi**.

Đây không phải yêu cầu mọi mutable object phải giữ equality mãi mãi. Nếu class cho sửa state tham gia equality thì kết quả có thể thay đổi; điều đó đặc biệt nguy hiểm khi object đang là key trong `HashMap`/phần tử của `HashSet`.

### 3.5. So sánh với `null`

Với mọi object `x` không null:

~~~java
x.equals(null) == false
~~~

Một implementation tốt trả false, **không ném `NullPointerException`** chỉ vì tham số `other` null.

### 3.6. Hợp đồng đúng chưa đủ: `equals` cần trả lời đúng câu hỏi domain

Các tính chất trên đảm bảo một **quan hệ tương đương** hợp lệ về logic. Chúng không tự quyết định tiêu chí bằng nhau nào có ích. Hai `Money` có amount 10 nhưng khác currency không nên bằng nhau; hai event logs có cùng timestamp chưa chắc cùng identity.

Trước khi viết code, hãy công bố các fields/quy tắc tham gia equality. Sau đó mới bảo vệ năm tính chất.

## 4. Mối liên hệ bắt buộc với `hashCode()`

Hợp đồng `Object.hashCode` có ba ý quan trọng:

1. Trong một lần thực thi ứng dụng Java, nếu không sửa thông tin tham gia kiểm tra `equals`, nhiều lần gọi `hashCode()` trên cùng object phải trả cùng `int` (không yêu cầu giữ nguyên giữa các lần chạy chương trình).
2. Nếu `a.equals(b)` là `true`, **`a.hashCode() == b.hashCode()` phải true**.
3. Nếu `a.equals(b)` là `false`, hash codes **không bắt buộc khác nhau**. Hash collision là hành vi hợp lệ.

Viết ngắn:

~~~text
a.equals(b) == true
              |
              v
a.hashCode() == b.hashCode()

Nhưng:

a.hashCode() == b.hashCode()
              |
              +-- KHÔNG suy ra a.equals(b)
~~~

### 4.1. Vì sao Java cần hợp đồng kép?

Hash-based collections dùng hash code để phân phối/tìm ứng viên trong cấu trúc dữ liệu và dùng equality để phân biệt keys đúng. Nếu hai keys được xem là equal nhưng lại có hash codes khác, việc tìm kiếm có thể đi đến vùng chứa không đúng và trả “không có” dù domain nói “cùng key”.

Mặt khác, **hai keys không bằng nhau có thể có cùng hash code**. Collection phải kiểm tra `equals` khi cần để vẫn phân biệt chúng.

### 4.2. Hash code không phải số định danh duy nhất

`hashCode()` trả một `int` 32 bit; số lượng objects/value combinations có thể nhiều hơn số lượng hash codes. Collision là điều không thể tránh về mặt nguyên lý khi miền giá trị lớn hơn miền 32 bit.

Bởi vậy:

- Không viết `if (a.hashCode() == b.hashCode()) return true;` để thay `equals`.
- Không dùng hash code làm primary key trong database.
- Không cho rằng `System.identityHashCode` đảm bảo unique.
- Không lưu hash làm chữ ký kiểm tra an toàn/bảo mật; hashCode không phải cryptographic hash.

## 5. Implementation đúng cho một immutable value object

Giả sử `StudentKey` được xác định bởi `schoolId` và `studentNumber`. Hai references khác nhau mô tả cùng cặp giá trị là equal.

Với một **`final` class**, ta có thể dùng `instanceof StudentKey` an toàn về subtype design vì class không thể được subclass.

### 5.1. Chương trình đầy đủ

Lưu **`ValueEqualityDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ValueEqualityDemo {
    static final class StudentKey {
        private final String schoolId;
        private final int studentNumber;

        StudentKey(String schoolId, int studentNumber) {
            this.schoolId = Objects.requireNonNull(
                    schoolId, "schoolId");
            this.studentNumber = studentNumber;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof StudentKey that)) {
                return false;
            }
            return studentNumber == that.studentNumber
                    && schoolId.equals(that.schoolId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(schoolId, studentNumber);
        }
    }

    public static void main(String[] args) {
        StudentKey a = new StudentKey("S-1", 7);
        StudentKey b = new StudentKey("S-1", 7);
        StudentKey c = new StudentKey("S-1", 8);

        System.out.println("same reference=" + (a == b));
        System.out.println("a equals b=" + a.equals(b));
        System.out.println("b equals a=" + b.equals(a));
        System.out.println("a equals c=" + a.equals(c));
        System.out.println("a equals null=" + a.equals(null));
        System.out.println("equal hashes=" +
                (a.hashCode() == b.hashCode()));

        Set<StudentKey> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(c);

        System.out.println("set size=" + set.size());
        System.out.println("contains equal key=" +
                set.contains(new StudentKey("S-1", 7)));
    }
}
~~~

Chạy:

~~~bash
javac ValueEqualityDemo.java
java ValueEqualityDemo
~~~

**Output:**

~~~text
same reference=false
a equals b=true
b equals a=true
a equals c=false
a equals null=false
equal hashes=true
set size=2
contains equal key=true
~~~

**Tại sao implementation này đúng?**

- `StudentKey` được khai báo `final`, chặn subclass thêm state rồi phá equality contract.
- Fields `schoolId` và `studentNumber` là private final; `String` immutable.
- `this == other` là một tối ưu hợp lệ: cùng reference chắc chắn equal trong thiết kế này.
- Pattern `instanceof StudentKey that` vừa kiểm tra kiểu vừa ràng buộc reference có kiểu đúng; null không match.
- Logic `equals` so **cả hai fields** trong tiêu chí.
- `hashCode` dùng **đúng hai fields** tham gia equality.
- Hai keys cùng giá trị có cùng hash theo contract; `HashSet` chỉ lưu một đại diện cho nhóm equal.
- Không dựa vào thứ tự iteration hoặc giá trị hash cụ thể.

### 5.2. Khi nào dùng `Objects.equals`?

Nếu field có thể null:

~~~java
return age == that.age
        && Objects.equals(nickname, that.nickname);
~~~

`Objects.equals(a,b)` xử lý null thuận tiện: hai null trả true, một null trả false, hai non-null dùng `a.equals(b)`.

Nếu constructor đã dùng `Objects.requireNonNull(name)` và field luôn non-null, viết `name.equals(that.name)` là hợp lý, miễn invariant thực sự được bảo vệ.

### 5.3. Vì sao signature phải là `equals(Object)`?

Override chuẩn:

~~~java
@Override
public boolean equals(Object other) {
    // ...
}
~~~

**Không** viết thay bằng:

~~~java
public boolean equals(StudentKey other) {
    // ...
}
~~~

vì đây chỉ là **overload** với parameter subtype, không override `Object.equals(Object)`. Collections thường làm việc với API `equals(Object)`, nên overload không giải quyết identity-based equality đã kế thừa.

`@Override` giúp compiler phát hiện sai chữ ký. Không được giảm quyền truy cập xuống protected/private khi override method public của Object.

## 6. `hashCode` có thể triển khai như thế nào?

Các lựa chọn phổ biến:

~~~java
@Override
public int hashCode() {
    return Objects.hash(schoolId, studentNumber);
}
~~~

`Objects.hash(Object...)` tạo hash dựa trên các arguments bằng cách dùng cơ chế hashing cho chuỗi giá trị (có thể có boxing và varargs allocation). Với các value objects nhỏ, cách viết này dễ đọc.

Một lựa chọn tính tay:

~~~java
@Override
public int hashCode() {
    int result = schoolId.hashCode();
    result = 31 * result + Integer.hashCode(studentNumber);
    return result;
}
~~~

Công thức kết hợp với 31 là một convention phổ biến, **không bắt buộc** bởi hợp đồng Java. Cả hai có thể đúng nếu:

- Dựa trên **cùng dữ liệu** quyết định `equals`.
- Trả một `int` nhất quán khi dữ liệu không đổi.
- Không dùng randomness, timestamp hay identity nếu equality thuần giá trị đòi hash đồng nhất.

### 6.1. Có bắt buộc mọi field nằm trong `hashCode` không?

Không, nhưng các fields được chọn phải bảo đảm rằng **nếu equal thì hash equal**. `hashCode() { return 1; }` thỏa hợp đồng đúng về mặt logic, nhưng hiệu năng hash collections thường rất kém vì collisions.

Trong thực tế nên dùng các equality-relevant fields để phân phối tốt. **Không đưa thêm mutable unrelated field** vào hash nếu `equals` không xét field đó, vì các equal objects có thể mang giá trị trường phụ khác và sinh hash khác — vi phạm contract.

### 6.2. Có thể cache hash code không?

Với immutable value objects, việc cache hash có thể hợp lý nếu phép tính đắt và được gọi nhiều. Nhưng phải triển khai đúng cả thread safety/publication và giá trị 0 (nếu dùng 0 làm sentinel), tránh tạo race về dữ liệu chưa hoàn tất.

Đối với objects mutable tham gia equality, cached hash dễ trở thành **stale hash** sau mutation; không nên cache nếu chưa quản lý invalidation và contract rõ.

## 7. Hậu quả khi `equals` đúng nhưng `hashCode` sai

Giả sử class định nghĩa equality theo `id`, nhưng hash theo một field `slot` khác **không** tham gia `equals`. Hai objects cùng id và khác slot sẽ bằng nhau nhưng có hash code khác.

Đây là **lỗi hợp đồng**, không phải collision thông thường.

### 7.1. Chương trình cố ý vi phạm

Lưu **`BrokenHashContractDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class BrokenHashContractDemo {
    static final class BrokenKey {
        private final int id;
        private final int slot;

        BrokenKey(int id, int slot) {
            this.id = id;
            this.slot = slot;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BrokenKey key
                    && id == key.id;
        }

        @Override
        public int hashCode() {
            return slot; // SAI: slot không thuộc equals.
        }
    }

    public static void main(String[] args) {
        BrokenKey a = new BrokenKey(7, 1);
        BrokenKey b = new BrokenKey(7, 2);

        System.out.println("equals=" + a.equals(b));
        System.out.println("hashes equal=" +
                (a.hashCode() == b.hashCode()));

        Set<BrokenKey> set = new HashSet<>();
        set.add(a);
        System.out.println("contains b=" + set.contains(b));
        set.add(b);
        System.out.println("set size=" + set.size());

        Map<BrokenKey, String> map = new HashMap<>();
        map.put(a, "found");
        System.out.println("lookup b=" + map.get(b));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac BrokenHashContractDemo.java
java BrokenHashContractDemo
~~~

**Output trên JDK 17 thông dụng theo `HashMap` implementation:**

~~~text
equals=true
hashes equal=false
contains b=false
set size=2
lookup b=null
~~~

Phân tích:

- `a.equals(b)` true vì id cùng là 7.
- `a.hashCode()==1`, `b.hashCode()==2`, bất chấp equality nói chúng bằng nhau.
- Với hashing của JDK 17, hai hash values này được phân phối khác, nên set không tìm được b qua entry a và chấp nhận cả hai.
- Map đã lưu a, nhưng `map.get(b)` không truy ra cùng entry ở trường hợp này.
- **Lỗi gốc nằm ở class BrokenKey**, không phải `HashSet` hay `HashMap`. Khi key vi phạm contract, đừng yêu cầu collections cho kết quả “đúng theo equals” trong mọi tình huống.

Đây là **anti-example có chủ đích**, không tái sử dụng thiết kế này trong production.

### 7.2. Sửa đúng

Nếu identity theo `id`, viết:

~~~java
@Override
public int hashCode() {
    return Integer.hashCode(id);
}
~~~

Hoặc nếu `slot` cũng thuộc nghĩa equality, thêm nó vào **cả `equals` và `hashCode`**. Quyết định trước về domain, rồi đưa cả hai methods theo cùng định nghĩa.

## 8. Collision hợp lệ: hash bằng nhau nhưng objects khác nhau

Một số học viên kết luận sai rằng “hai objects có cùng hash là bằng nhau”. Điều đó **không đúng**.

### 8.1. Chương trình collision có chủ đích nhưng hợp đồng đúng

Lưu **`HashCollisionDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class HashCollisionDemo {
    static final class Key {
        private final String id;

        Key(String id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Key key
                    && java.util.Objects.equals(id, key.id);
        }

        @Override
        public int hashCode() {
            return 1; // Đúng contract, nhưng phân phối rất kém.
        }
    }

    public static void main(String[] args) {
        Key a = new Key("A");
        Key b = new Key("B");
        Key equalA = new Key("A");

        System.out.println("a equals b=" + a.equals(b));
        System.out.println("a equals equalA=" + a.equals(equalA));
        System.out.println("a and b hashes equal=" +
                (a.hashCode() == b.hashCode()));

        Set<Key> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(equalA);
        System.out.println("set size=" + set.size());

        Map<Key, String> map = new HashMap<>();
        map.put(a, "first");
        map.put(b, "second");

        System.out.println("map A=" + map.get(equalA));
        System.out.println("map B=" + map.get(b));
    }
}
~~~

Chạy:

~~~bash
javac HashCollisionDemo.java
java HashCollisionDemo
~~~

Output:

~~~text
a equals b=false
a equals equalA=true
a and b hashes equal=true
set size=2
map A=first
map B=second
~~~

**Kết luận:**

- `a` và `b` khác id, nên `equals` false dù hashes cùng 1.
- `a` và `equalA` cùng id, nên equal và hash equal.
- `HashSet` vẫn lưu hai nhóm keys A và B riêng.
- `HashMap` vẫn lấy đúng values theo equality dù collision.
- Constant hash không phá contract nhưng khiến hash collections mất lợi thế phân phối; cần hash phân tán đủ tốt khi data lớn.

Không dùng một collision để kết luận `hashCode` “không quan trọng”. Collision **được phép**; vi phạm equal→same-hash mới là lỗi nghiêm trọng.

## 9. `HashMap` và `HashSet` sử dụng equality như thế nào?

Ở mức khái niệm:

1. Khi `put`/`add`, collection lấy hash code của key/element.
2. Dựa trên hashing structure hiện hành, nó xác định vùng chứa ứng viên.
3. Khi cần, collection dùng equality để xác định có key/element tương đương đã tồn tại hay chưa.
4. Khi `get`/`contains`/`remove`, key tìm kiếm phải còn có hash/equality tương thích để định vị đúng entry.

**Không viết thuật toán giả cứng rằng HashMap luôn dùng đúng số buckets, đúng threshold hoặc đúng thứ tự duyệt** trong mọi Java implementations. Hợp đồng API quan trọng hơn chi tiết tối ưu runtime.

### 9.1. HashSet dùng cơ chế gì?

`HashSet` là set theo hashing; các phần tử không trùng nhau theo equality contract của nó. Nó không cung cấp thứ tự duyệt đáng tin như một phần hợp đồng.

`LinkedHashSet` cung cấp thứ tự iteration theo hợp đồng riêng, và `TreeSet` dựa trên ordering/comparator thay vì hashing cho khái niệm phần tử trùng. Vì vậy equality của TreeSet được quyết định bởi comparison trong các thao tác set tương ứng; cần đảm bảo ordering consistent with equals nếu muốn hai collections hiểu “trùng nhau” như nhau.

### 9.2. HashMap key `null`

`HashMap` cho phép một `null` key theo API (và nhiều null values), khác với một số implementations khác như `Hashtable` hay `ConcurrentHashMap` về chính sách null. Không có instance method nào được gọi trên null để lấy hashCode theo nghĩa Java source-level; collection xử lý trường hợp đó theo contract.

Đừng tự viết `key.hashCode()` trước `put` nếu API cho key nullable mà bạn chưa xử lý null.

## 10. Mutable hash key: khi methods hợp đồng đúng nhưng *cách dùng* sai

Hai methods `equals/hashCode` có thể nhất quán với **state hiện tại** nhưng key vẫn không an toàn cho `HashMap` nếu state được sửa sau `put`. Hash collection không theo dõi setters và không tự reindex entry theo giá trị hash mới.

~~~java
record StableKey(int id) {}
~~~

Đây là record hợp lệ với một primitive immutable component; nó tránh được lỗi **đổi field dùng để so sánh sau insertion**. `final` trên biến tham chiếu không có tác dụng tương đương: `final MutableKey key` vẫn cho phép setter thay state bên trong object.

| Khi thiết kế key | Kết quả cần bảo đảm |
| --- | --- |
| Key dựa trên immutable value | Hash và equality-relevant state không đổi trong thời gian lưu |
| Key dựa trên ID được gán sau khi insert | Rủi ro hash/equality thay đổi, cần tách lifecycle hoặc cấp ID trước |
| Key được sửa khi đang có trong Map | Không dựa vào lookup/remove ổn định; quản lý remove-before-change/reinsert với synchronization nếu cần |
| Mutable object chỉ là **value** trong Map | Mutation không tự đổi hash bucket của key, dù có rủi ro state/concurrency khác |

Điểm dạy chính ở đây là **hợp đồng so sánh và hợp đồng sử dụng collection là hai tầng khác nhau**. Bài mutable fields kế tiếp dùng tình huống HashSet/HashMap, kể cả trường hợp hash chưa đổi nhưng equality đổi, để làm rõ hậu quả, các chiến lược sửa và caveat của implementation.

## 11. `getClass()` hay `instanceof` trong `equals`?

Hai cách kiểm tra kiểu thường gặp:

**Cách A — `instanceof`:**

~~~java
if (!(other instanceof Point point)) {
    return false;
}
~~~

Thường cho phép subclasses của Point match. Nếu một subclass thêm state tham gia equality, nguy cơ **bất đối xứng** xuất hiện khi superclass và subclass định nghĩa tiêu chí khác nhau.

**Cách B — kiểm tra đúng runtime class:**

~~~java
if (other == null || getClass() != other.getClass()) {
    return false;
}
~~~

Hai objects khác subclass sẽ không bằng nhau, ngay cả khi có fields chung. Cách này thường dễ giữ symmetry hơn nếu class hierarchy yêu cầu equality chỉ trong đúng class.

**Không có lựa chọn máy móc đúng cho mọi domain.** Vấn đề là subtype equality contract và khả năng mở rộng class.

### 11.1. Nếu class là `final`

Với `final class Value`, không có subclass hợp lệ; `instanceof Value` là đủ để xác nhận đúng kiểu object không null, giảm phức tạp đáng kể.

Immutable final value classes hoặc Java records thường là lựa chọn an toàn cho value semantics khi không cần subclassing.

### 11.2. Nếu class có thể được kế thừa

Cần cân nhắc:

- Subclass có fields mới **tham gia equality không**?
- Parent có cho equality cross-type không?
- Giữ symmetry/transitivity bằng cách nào?
- Có cần sealed hierarchy hoặc shared identity semantics?
- Có thể tránh inheritance cho value types, thay bằng composition không?

Một quy ước `canEqual` có thể hỗ trợ thiết kế kế thừa phức tạp, nhưng cần triển khai có hiểu biết và kiểm thử kỹ. Một cách đơn giản khác là dùng exact-class equality hoặc cấm subclassing của value class.

## 12. Ví dụ sai: vi phạm đối xứng do kế thừa

Lưu **`BrokenSymmetryDemo.java`**:

~~~java
public class BrokenSymmetryDemo {
    static class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Point point
                    && x == point.x && y == point.y;
        }

        @Override
        public int hashCode() {
            return java.util.Objects.hash(x, y);
        }
    }

    static final class ColorPoint extends Point {
        private final String color;

        ColorPoint(int x, int y, String color) {
            super(x, y);
            this.color = color;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof ColorPoint point
                    && super.equals(point)
                    && java.util.Objects.equals(color, point.color);
        }

        @Override
        public int hashCode() {
            return java.util.Objects.hash(super.hashCode(), color);
        }
    }

    public static void main(String[] args) {
        Point base = new Point(1, 2);
        ColorPoint colored = new ColorPoint(1, 2, "red");

        System.out.println("base equals colored=" +
                base.equals(colored));
        System.out.println("colored equals base=" +
                colored.equals(base));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac BrokenSymmetryDemo.java
java BrokenSymmetryDemo
~~~

Output:

~~~text
base equals colored=true
colored equals base=false
~~~

**Vì sao sai?**

- `Point.equals` dùng `instanceof Point`, nên ColorPoint cũng match nếu coordinates bằng nhau.
- `ColorPoint.equals` dùng `instanceof ColorPoint`, từ chối một Point thuần.
- `base.equals(colored)` true nhưng `colored.equals(base)` false → **vi phạm symmetry**.
- Hai classes còn có nguy cơ vi phạm equal→same-hash vì base và colored có thể khác hash, làm tình hình tệ hơn.

**Không khuyến nghị** sửa bằng cách xóa so sánh color trong subclass một cách tùy tiện nếu color thực sự quan trọng với domain. Hãy thống nhất equality contract từ cấp thiết kế type hierarchy.

## 13. Một lựa chọn rõ: equality chỉ trong cùng concrete class

Lưu **`ExactClassEqualityDemo.java`**:

~~~java
public class ExactClassEqualityDemo {
    static class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (other == null || getClass() != other.getClass()) {
                return false;
            }
            Point point = (Point) other;
            return x == point.x && y == point.y;
        }

        @Override
        public int hashCode() {
            return java.util.Objects.hash(getClass(), x, y);
        }
    }

    static final class ColorPoint extends Point {
        private final String color;

        ColorPoint(int x, int y, String color) {
            super(x, y);
            this.color = color;
        }

        @Override
        public boolean equals(Object other) {
            return super.equals(other)
                    && java.util.Objects.equals(
                            color, ((ColorPoint) other).color);
        }

        @Override
        public int hashCode() {
            return java.util.Objects.hash(super.hashCode(), color);
        }
    }

    public static void main(String[] args) {
        Point p = new Point(1, 2);
        ColorPoint red = new ColorPoint(1, 2, "red");
        ColorPoint anotherRed = new ColorPoint(1, 2, "red");

        System.out.println("p equals red=" + p.equals(red));
        System.out.println("red equals p=" + red.equals(p));
        System.out.println("two red=" + red.equals(anotherRed));
        System.out.println("red hash equal=" +
                (red.hashCode() == anotherRed.hashCode()));
    }
}
~~~

Chạy:

~~~bash
javac ExactClassEqualityDemo.java
java ExactClassEqualityDemo
~~~

Stdout:

~~~text
p equals red=false
red equals p=false
two red=true
red hash equal=true
~~~

**Giải thích:**

- `getClass()` chặn equality giữa Point thuần và ColorPoint, bảo vệ symmetry trong ví dụ.
- Khi `ColorPoint.equals(other)` thực thi, `super.equals(other)` chỉ true với object có **exact runtime class ColorPoint**, nên cast sau đó an toàn ở nhánh này.
- ColorPoint bổ sung `color` vào equality và hash.
- Cách này chỉ là **một thiết kế**: nó nói hai subtypes khác nhau không equal, dù fields chung giống nhau. Hãy dùng khi đó là điều domain muốn.
- Nếu superclass được framework proxy/subclass động, exact-class check có thể ảnh hưởng equality; phải cân nhắc framework và domain identity cụ thể, không có giải pháp chung cho mọi ORM proxy.

### 13.1. Có nên cho subclass đổi meaning của equality không?

Khi muốn extension không làm thay equality contract, tốt nhất thường là thiết kế value object **final**, hoặc giữ một immutable stable identity được superclass kiểm soát và quy định rõ subclasses không thay ngữ nghĩa equality.

Với entity hierarchies phức tạp, nên cân nhắc mô hình composition, sealed types hoặc identifiers thay vì các bộ `equals` override cạnh tranh nhau.

## 14. Null fields và `Objects.equals`

Field nullable cần được so sánh an toàn:

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof Contact that)) {
        return false;
    }
    return java.util.Objects.equals(nickname, that.nickname)
            && java.util.Objects.equals(email, that.email);
}

@Override
public int hashCode() {
    return java.util.Objects.hash(nickname, email);
}
~~~

Đây là **method snippet** của một class `Contact` có fields `nickname`/`email` tương ứng, không phải file Java độc lập.

`Objects.equals(null, null)` trả true; `Objects.equals(null, "A")` false; hai non-null objects được so theo `equals` của object thứ nhất.

**Đừng** viết `nickname.equals(that.nickname)` nếu `nickname` có thể null, trừ khi đã kiểm tra. Null không được gây NPE ngoài ý muốn ở `equals(Object)`.

### 14.1. Order các so sánh có thể tối ưu hóa nhưng không đổi semantics

Với nhiều fields, nên so những primitive/stable values rẻ trước, rồi tới collection/string nếu muốn. Tuy nhiên, nếu một field comparison có side effect hoặc phụ thuộc thời gian, bản thân equality contract đã khó giữ.

`equals` nên là thao tác **thuần** về mặt quan sát: không mutate objects, không thực hiện I/O bất ngờ, không thay trạng thái tham gia equality.

## 15. Arrays: `Object.equals` và `Arrays.equals` không giống nhau

Java arrays là objects. Một array thông thường **không override `Object.equals` để so từng phần tử**.

~~~java
int[] a = {1, 2, 3};
int[] b = {1, 2, 3};
~~~

`a.equals(b)` false vì là hai array instances khác nhau, dù nội dung giống nhau.

Muốn so nội dung arrays:

- `Arrays.equals(int[], int[])` với primitive arrays một chiều.
- `Arrays.equals(Object[], Object[])` với object arrays một chiều, dùng equality của elements.
- `Arrays.deepEquals(Object[], Object[])` cho nested object arrays cần deep content comparison theo ngữ nghĩa API.
- `Arrays.hashCode(...)` hoặc `Arrays.deepHashCode(...)` tương ứng để xây hash nhất quán.

### 15.1. Tại sao dùng `Objects.hash(array)` dễ nhầm?

`Objects.hash(Object...)` dùng varargs. Nếu truyền một array reference, cách compiler xây arguments có thể khác với ý định và kiểu array; tuyệt đối **không coi Objects.hash(array) mặc nhiên là content hash của mọi mảng**.

Quy tắc an toàn khi class equality dựa vào nội dung `int[]`: dùng **`Arrays.equals` và `Arrays.hashCode`** cùng nhau. Với multi-dimensional/nested arrays dùng cặp deep methods khi phù hợp.

## 16. Chương trình: arrays và defensive copying

Lưu **`ArrayEqualityDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayEqualityDemo {
    record RawRecord(int[] values) {
    }

    static final class IntArrayKey {
        private final int[] values;

        IntArrayKey(int[] input) {
            values = input.clone();
        }

        int[] values() {
            return values.clone();
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof IntArrayKey key
                    && Arrays.equals(values, key.values);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        int[] a = {1, 2};
        int[] b = {1, 2};

        System.out.println("array equals=" + a.equals(b));
        System.out.println("content equals=" + Arrays.equals(a, b));

        RawRecord r1 = new RawRecord(a);
        RawRecord r2 = new RawRecord(b);
        System.out.println("record arrays equal=" + r1.equals(r2));

        IntArrayKey k1 = new IntArrayKey(a);
        IntArrayKey k2 = new IntArrayKey(b);

        System.out.println("keys equal=" + k1.equals(k2));
        System.out.println("key hashes equal=" +
                (k1.hashCode() == k2.hashCode()));

        a[0] = 9;
        int[] escaped = k1.values();
        escaped[1] = 8;

        System.out.println("stored first=" + k1.values()[0]);
        System.out.println("stored second=" + k1.values()[1]);
    }
}
~~~

Chạy:

~~~bash
javac ArrayEqualityDemo.java
java ArrayEqualityDemo
~~~

Output:

~~~text
array equals=false
content equals=true
record arrays equal=false
keys equal=true
key hashes equal=true
stored first=1
stored second=2
~~~

**Giải thích:**

- `a.equals(b)` so identity của hai arrays.
- `Arrays.equals(a,b)` so nội dung hai primitive arrays.
- `RawRecord` mặc định sinh `equals` dựa vào component values, nhưng component kiểu array được so **theo identity**, không deep array contents.
- `IntArrayKey` dùng content equality và content hash code.
- Constructor **clone input array**, accessor cũng **clone output**, nên caller sửa `a` hoặc `escaped` không mutate internal array/hashing state của key.
- Từ góc độ hash collections, đây là value key ổn định nếu internal array không bị lộ từ nơi khác.

**Không kết luận mọi record là deep immutable chỉ vì components final.** Với array/list mutable components, generated accessor có thể lộ reference mutable; cần thiết kế defensive copy khi cần.

## 17. Nested arrays và `deepEquals`/`deepHashCode`

Với nested arrays:

~~~java
int[][] a = {{1, 2}, {3}};
int[][] b = {{1, 2}, {3}};
~~~

`Arrays.equals(a,b)` dùng element equality cho từng phần tử bên ngoài. Mỗi phần tử là `int[]` object nên vẫn so identity nếu không dùng deep semantics. Muốn so giá trị lồng nhau, `Arrays.deepEquals(Object[],Object[])` có thể được áp dụng cho `int[][]` vì đây là một array chứa các `int[]` objects.

### 17.1. Demo nested arrays

Lưu **`DeepArrayEqualityDemo.java`**:

~~~java
import java.util.Arrays;

public class DeepArrayEqualityDemo {
    public static void main(String[] args) {
        int[][] first = {{1, 2}, {3}};
        int[][] second = {{1, 2}, {3}};

        System.out.println("shallow=" +
                Arrays.equals(first, second));
        System.out.println("deep=" +
                Arrays.deepEquals(first, second));
        System.out.println("deep hash equal=" +
                (Arrays.deepHashCode(first) ==
                        Arrays.deepHashCode(second)));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DeepArrayEqualityDemo.java
java DeepArrayEqualityDemo
~~~

Output:

~~~text
shallow=false
deep=true
deep hash equal=true
~~~

**Cảnh báo:** các `Arrays.deep...` methods không nên được xem như công cụ tổng quát xử lý mọi **cyclic array graph**. Với nested reference arrays có cycles, recursive deep equality/hashing có thể không dừng/overflow theo các điều kiện API. Nếu domain cho phép graph có cycle, hãy thiết kế traversal và equality có visited/identity tracking thích hợp thay vì blindly deep hashing.

## 18. Records sinh sẵn `equals`, `hashCode` và `toString`

Java 17 có **record classes** ổn định. Một record đơn giản:

~~~java
record StudentKey(String schoolId, int studentNumber) {
}
~~~

tự cung cấp constructor/accessors và triển khai `equals`/`hashCode`/`toString` theo **record components**.

### 18.1. Khi nào record là lựa chọn tốt?

Nếu object đại diện cho **một value tuple** với components tham gia equality, records giúp giảm boilerplate, cải thiện sự nhất quán và nói rõ dữ liệu là phần cốt lõi.

Nhưng:

- Record có component reference `List<X>` hoặc array thì shallow immutability vẫn là vấn đề.
- Muốn chuẩn hóa dữ liệu như email lowercase, cần thực hiện trong constructor hợp lệ.
- Đừng thay thế mọi entity bằng record nếu entity có identity/lifecycle riêng không trùng toàn bộ components.
- Generated equality phân biệt record type và components theo semantics record; không nhất thiết phù hợp mọi domain equivalence cần bỏ qua một số fields.

### 18.2. Chương trình immutable record key

Lưu **`RecordEqualityDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class RecordEqualityDemo {
    record EmailKey(String email) {
        EmailKey {
            Objects.requireNonNull(email, "email");
            email = email.trim().toLowerCase(Locale.ROOT);
            if (email.isEmpty()) {
                throw new IllegalArgumentException("empty email");
            }
        }
    }

    public static void main(String[] args) {
        EmailKey first = new EmailKey("  LAN@EXAMPLE.COM ");
        EmailKey second = new EmailKey("lan@example.com");
        EmailKey third = new EmailKey("minh@example.com");

        System.out.println("first=" + first.email());
        System.out.println("first equals second=" +
                first.equals(second));
        System.out.println("hashes equal=" +
                (first.hashCode() == second.hashCode()));

        Set<EmailKey> set = new HashSet<>();
        set.add(first);
        set.add(second);
        set.add(third);
        System.out.println("set size=" + set.size());
    }
}
~~~

Chạy:

~~~bash
javac RecordEqualityDemo.java
java RecordEqualityDemo
~~~

Output:

~~~text
first=lan@example.com
first equals second=true
hashes equal=true
set size=2
~~~

**Lưu ý về chuẩn hóa email:** lowercasing toàn bộ email ở đây chỉ là **quy tắc giả định của ví dụ**. Trong hệ thống mail thực, tiêu chí equivalence có thể phụ thuộc local-part, domain, quốc tế hóa và chính sách sản phẩm. Không dùng phép chuẩn hóa đơn giản này như đặc tả xác thực email phổ quát.

## 19. `String`, wrappers, enums và `BigDecimal`

Các classes thư viện Java định nghĩa equality theo contract riêng:

- `String.equals`: so nội dung ký tự có phân biệt hoa/thường.
- `Integer.equals`, `Long.equals`: so giá trị wrapper cùng loại tương ứng; `Integer.valueOf(7).equals(Long.valueOf(7))` false vì khác wrapper class.
- `Enum.equals`: enum instances có identity semantics theo singleton enum constants; thường so enum values bằng `==` là đúng và đọc rõ.
- `BigDecimal.equals`: xét cả **giá trị số và scale** theo contract; `compareTo` có thể coi những giá trị khác scale là tương đương về số.

### 19.1. BigDecimal: `equals` khác `compareTo()==0`

~~~java
new java.math.BigDecimal("2.0")
        .equals(new java.math.BigDecimal("2.00"))
~~~

trả `false`, vì scales khác. Nhưng `compareTo(...)` trả `0` vì bằng nhau về **numeric ordering**.

Đây không phải lỗi hợp đồng `equals`. Nó là quyết định của `BigDecimal` về equality và ordering, cần được hiểu khi dùng `HashSet` vs `TreeSet`.

### 19.2. Chương trình rõ ràng

Lưu **`BigDecimalEqualityDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalEqualityDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("equals=" + a.equals(b));
        System.out.println("compareTo=" + a.compareTo(b));
        System.out.println("hash equal=" +
                (a.hashCode() == b.hashCode()));

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(a);
        hashSet.add(b);

        Set<BigDecimal> treeSet = new TreeSet<>();
        treeSet.add(a);
        treeSet.add(b);

        System.out.println("HashSet size=" + hashSet.size());
        System.out.println("TreeSet size=" + treeSet.size());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac BigDecimalEqualityDemo.java
java BigDecimalEqualityDemo
~~~

Stdout:

~~~text
equals=false
compareTo=0
hash equal=false
HashSet size=2
TreeSet size=1
~~~

**Diễn giải:**

- `equals` phân biệt scale.
- `compareTo` đánh giá numeric ordering bằng 0.
- `HashSet` coi hai keys khác nhau.
- `TreeSet` với natural ordering dùng comparison bằng 0 để xác định equivalent elements, nên chỉ giữ một.
- Khi nghiệp vụ muốn so số tiền không phân biệt scale, hãy **chuẩn hóa biểu diễn/canonical form** hoặc định nghĩa một value type/Comparator nhất quán; không tự ép BigDecimal sửa hợp đồng.

### 19.3. Ordering “consistent with equals”

Một comparator/natural order được gọi là *consistent with equals* khi so sánh bằng 0 tương ứng equality cho các objects. Nếu không consistent, sorted collections có thể khác hash collections về khái niệm phần tử trùng.

Cân nhắc kỹ khi dùng `TreeSet`/`TreeMap` với `BigDecimal` hoặc comparator chỉ so một field rồi bỏ các fields phân biệt domain identity.

## 20. Floating point: `NaN`, `+0.0` và `-0.0`

Với primitives, `Double.NaN == Double.NaN` là false theo toán tử floating point equality. Nhưng wrapper `Double.equals` và value semantics của records có double components tuân hợp đồng có thể xem những bit patterns NaN tương ứng là equal; `+0.0` và `-0.0` được phân biệt theo wrapper equality.

### 20.1. Chương trình đối chiếu

Lưu **`FloatingEqualityDemo.java`**:

~~~java
public class FloatingEqualityDemo {
    record Measure(double value) {
    }

    public static void main(String[] args) {
        double nan = Double.NaN;

        System.out.println("primitive NaN==" + (nan == nan));
        System.out.println("Double NaN equals=" +
                Double.valueOf(nan).equals(Double.valueOf(nan)));

        Measure a = new Measure(Double.NaN);
        Measure b = new Measure(Double.NaN);
        Measure plus = new Measure(+0.0);
        Measure minus = new Measure(-0.0);

        System.out.println("record NaN equal=" + a.equals(b));
        System.out.println("record NaN hashes equal=" +
                (a.hashCode() == b.hashCode()));
        System.out.println("primitive zero equal=" +
                (+0.0 == -0.0));
        System.out.println("record zeros equal=" +
                plus.equals(minus));
    }
}
~~~

Chạy:

~~~bash
javac FloatingEqualityDemo.java
java FloatingEqualityDemo
~~~

Output:

~~~text
primitive NaN==false
Double NaN equals=true
record NaN equal=true
record NaN hashes equal=true
primitive zero equal=true
record zeros equal=false
~~~

**Vì sao quan trọng?**

Nếu tự viết `equals` dùng `value == that.value` cho field double, nó có thể khiến một object chứa NaN **không bằng chính nó** nếu không có identity shortcut — vi phạm reflexivity. `+0.0`/`-0.0` có thể được coi là bằng nhau với primitive `==` nhưng cho hash khác nếu hash dựa trên `Double.hashCode` — có nguy cơ vi phạm equal→same-hash.

Với floating point fields, dùng chiến lược nhất quán, ví dụ `Double.compare(a,b)==0` kết hợp `Double.hashCode(value)` nếu đó là ý nghĩa equality mong muốn; kiểm thử cả NaN và signed zeros.

**Đừng dùng tolerance kiểu `Math.abs(a-b)<epsilon` bừa bãi để định nghĩa `equals`.** Approximate comparisons có thể phá tính bắc cầu, không phù hợp khi dùng làm equivalence relation trong hash collections.

## 21. Vì sao so gần đúng với epsilon có thể phá tính bắc cầu?

Một anti-pattern:

~~~java
boolean approximatelyEqual(double a, double b) {
    return Math.abs(a - b) < 0.2;
}
~~~

Đây là method snippet dùng khi so số đo gần đúng, **không phải một implementation `equals` an toàn**. Chọn:

~~~text
a = 0.0
b = 0.15
c = 0.30

|a-b| = 0.15 < 0.2  => a ~ b
|b-c| = 0.15 < 0.2  => b ~ c
|a-c| = 0.30 >= 0.2 => a !~ c
~~~

Tính bắc cầu bị vi phạm. Điều này không cấm bạn dùng *approximate numeric comparison* trong tính toán, nhưng **đừng biến nó thành `Object.equals`** của một key nếu bạn không chứng minh được equivalence contract.

Nếu cần phân loại số đo thành các nhóm, hãy chọn quy tắc chuẩn hóa/quantization tạo **các nhóm ổn định**, rồi so các nhóm theo equality bắc cầu, hiểu rõ sai số nghiệp vụ.

## 22. `Objects.hash` và object graphs lồng nhau

`Objects.hash(field1, field2, ...)` giúp kết hợp hashes nhưng không tự làm sâu bất kỳ object graph nào.

Nếu field là một `List<String>`, `List.equals` theo API sẽ so nội dung phần tử theo thứ tự; `List.hashCode` được định nghĩa tương thích với content equality. Nếu field là custom class chưa override equals/hashCode, `Objects.hash` sẽ dùng identity-based semantics cho field ấy.

Nếu field là mutable collection, content equality và hash có thể **thay đổi khi collection đổi**. Vì vậy một key muốn ổn định nên dùng **immutable snapshot**, ví dụ `List.copyOf(input)` kết hợp immutable element types.

### 22.1. Phải xử lý cycles trong object graph

Nếu object A giữ B và B giữ A, tự viết:

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hash(other);
}
~~~

cho **cả A và B**, khiến hashing đi qua reference qua lại có thể đệ quy không dừng và gây `StackOverflowError`. `equals` cũng có nguy cơ tương tự khi duyệt mọi neighbor recursively.

Cách giải quyết tùy domain:

- So/hash theo **stable identity ID** thay vì toàn bộ graph.
- So các immutable value components không tạo cycles.
- Với graph equality thật sự, thiết kế thuật toán visited-pair/memoization phù hợp và định nghĩa equivalence chặt chẽ.
- Tránh tự động sinh `equals`/`hashCode` từ mọi bidirectional association của entities trong ORM.

## 23. Entity identity, generated IDs và lifecycle

Một entity thường có trạng thái thay đổi: `status`, `address`, `updatedAt`. Nếu đưa các fields này vào `equals`/`hashCode` và đưa entity vào HashSet trước khi mutation, collection có thể hỏng lookup.

Với database-backed entities, một lựa chọn phổ biến là dùng **stable business key** hoặc **ID đã được cấp trước khi object dùng làm hash key**. Nhưng phải xử lý trường hợp ID chưa có:

- Hai transient entities đều có id null, **không** tự có nghĩa chúng equal.
- Nếu ID được gán sau persist, hash theo ID có thể thay đổi trong lúc entity nằm trong HashSet.
- ORM proxies có thể khiến `getClass()` và `instanceof` hoạt động khác kỳ vọng nếu hierarchy được tăng cường.
- Persistence identity, Java object identity và business equality **không phải luôn cùng một khái niệm**.

Không có một template equals/hashCode áp dụng đúng cho mọi JPA/domain entity. Cần theo hướng dẫn framework cụ thể, state lifecycle và các tests tương ứng.

### 23.1. Với immutable value object

Nếu object chỉ biểu diễn giá trị như `Coordinates`, `Money` hoặc `StudentKey`, Java record/final class với immutable fields thường dễ đúng hơn. Khi domain identity biến đổi theo thời gian, đừng giả vờ đó là immutable value key.

### 23.2. Với cache và distributed system

`hashCode()` của Java không phải stable global key across nodes/processes. Không dùng để làm cache key serialization hoặc sharding fingerprint dài hạn nếu không có hashing specification riêng ổn định. Dùng business identifier/serialization format và hash algorithm được định nghĩa riêng khi cần.

## 24. Vai trò của `equals` khi so các collections

Java collections định nghĩa equality theo loại:

- `List.equals`: hai lists bằng nhau nếu các elements tương ứng bằng nhau **và cùng thứ tự**.
- `Set.equals`: hai sets bằng nhau nếu chứa cùng elements theo contract, **không dựa vào iteration order**.
- `Map.equals`: hai maps bằng nhau theo mappings tương ứng.
- `Arrays.equals`: một chiều theo contents (với overload phù hợp); array `equals` instance vẫn identity.
- `Collections.unmodifiableList`: wrapper ngăn sửa qua view, **không** tự bảo đảm backing list không bị nơi khác mutate.
- `List.copyOf`: snapshot không sửa được về cấu trúc, nhưng elements vẫn có thể là mutable references.

Nếu bạn dùng collection mutable làm field của key, hãy cân nhắc thay bằng snapshot immutable/defensive copy; nếu elements mutable, snapshot list vẫn không deep-immutable.

### 24.1. Ví dụ list/set equality không phụ thuộc hash cụ thể

Lưu **`CollectionEqualityDemo.java`**:

~~~java
import java.util.List;
import java.util.Set;

public class CollectionEqualityDemo {
    public static void main(String[] args) {
        List<String> ab = List.of("A", "B");
        List<String> ba = List.of("B", "A");

        System.out.println("list order matters=" + ab.equals(ba));

        Set<String> first = Set.of("A", "B");
        Set<String> second = Set.of("B", "A");

        System.out.println("set order ignored=" +
                first.equals(second));
        System.out.println("set hashes equal=" +
                (first.hashCode() == second.hashCode()));
    }
}
~~~

Chạy:

~~~bash
javac CollectionEqualityDemo.java
java CollectionEqualityDemo
~~~

Output:

~~~text
list order matters=false
set order ignored=true
set hashes equal=true
~~~

`Set.of` có thể duyệt theo thứ tự khác nhau giữa runs; ví dụ **không in collection** và không dựa vào thứ tự đó. Nó chỉ in các thuộc tính equality/hash Java bảo đảm.

## 25. Dùng `equals` ở đâu trong ứng dụng?

Một số ví dụ thực tế:

- `HashSet.contains`: kiểm tra đã có element tương đương.
- `HashMap.get`: tìm value theo key tương đương.
- `List.contains`: dùng equality của elements để tìm.
- `List.indexOf`: so element để tìm vị trí.
- `Objects.equals(a,b)`: so an toàn khi một/both nullable.
- Unit tests như `assertEquals(expected,actual)`: thông thường gọi equality theo framework API; nếu class chưa override thì hai instances riêng không bằng nhau.
- Domain validation, deduplication, caching, grouping theo keys.

Cần biết **semantics của container**. Ví dụ `IdentityHashMap` dùng reference identity semantics thay vì logic equality kiểu HashMap trong các thao tác key; nó hữu ích ở các tình huống chuyên biệt như graph visited identity, nhưng không dùng thay HashMap theo thói quen.

### 25.1. Khi nào dùng `==` cho references?

`==` đúng khi câu hỏi là **có phải chính cùng object instance không?**

Ví dụ:
- So enum values vì enum constants có identity semantics phù hợp.
- Xác nhận aliasing (hai biến cùng trỏ object).
- Graph traversal cần identity-based visited set.
- Kiểm tra `this == other` là đường tắt trước khi so fields trong `equals`.

Không dùng `==` thay logical equality của String, BigDecimal, records hoặc value classes trừ khi thật sự cần identity.

## 26. `IdentityHashMap` khác `HashMap`

`IdentityHashMap` so keys bằng `==` và dùng identity-based hashing semantics, khác `HashMap` vốn dựa trên `equals`/`hashCode`.

### 26.1. Chương trình nhìn thấy sự khác biệt

Lưu **`IdentityMapDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class IdentityMapDemo {
    public static void main(String[] args) {
        String first = new String("A");
        String second = new String("A");

        Map<String, Integer> logical = new HashMap<>();
        Map<String, Integer> identity = new IdentityHashMap<>();

        logical.put(first, 1);
        logical.put(second, 2);

        identity.put(first, 1);
        identity.put(second, 2);

        System.out.println("equals=" + first.equals(second));
        System.out.println("same identity=" + (first == second));
        System.out.println("HashMap size=" + logical.size());
        System.out.println("IdentityHashMap size=" + identity.size());
    }
}
~~~

Chạy:

~~~bash
javac IdentityMapDemo.java
java IdentityMapDemo
~~~

Output:

~~~text
equals=true
same identity=false
HashMap size=1
IdentityHashMap size=2
~~~

Với HashMap, keys bằng nhau theo String.equals, nên entry thứ hai thay value. Với IdentityHashMap, hai String instances là hai keys phân biệt dù nội dung bằng nhau.

**Không nên dùng IdentityHashMap chỉ để “sửa” một key có equals/hashCode sai.** Nó đổi khái niệm equality của map; nếu nghiệp vụ đòi logical keys thì cần sửa key.

## 27. Thread safety và tính ổn định

`equals`/`hashCode` thông thường không tự đồng bộ. Nếu fields tham gia so sánh bị thay bởi thread khác, hai lời gọi liên tiếp có thể quan sát các snapshots khác nhau hoặc gặp data race/visibility issues.

Một immutable value key được công bố an toàn thường dễ dùng chung threads hơn mutable entity key. Nhưng:

- `final` reference tới mutable collection không làm nội dung collection immutable.
- Một method `equals` gọi getters có side effects hoặc phụ thuộc clock/random có thể không nhất quán.
- Nếu object graph thay đổi đồng thời, “so từng field lần lượt” không nhất thiết là atomic snapshot.
- `ConcurrentHashMap` giúp operations trên map có semantics concurrency thích hợp, **không làm mutable keys trở nên ổn định**.

Trong code concurrent, hãy thiết kế equality dựa trên immutable/stable state hoặc có synchronization/snapshot phù hợp với nhu cầu.

## 28. Kiểm thử hợp đồng `equals` và `hashCode`

Một bộ tests nên kiểm tra:

1. **Reflexive:** `a.equals(a)`.
2. **Symmetric:** `a.equals(b) == b.equals(a)` cho cả equal và unequal pairs.
3. **Transitive:** nếu a=b và b=c thì a=c.
4. **Consistent:** gọi nhiều lần khi fields không đổi.
5. **Non-null:** `!a.equals(null)`.
6. **Equal→same-hash:** `a.equals(b)` thì hashes bằng nhau.
7. **Unequal:** thử ít nhất một field khác nhau; không đòi hashes phải khác.
8. **HashSet/HashMap:** thêm các equivalent keys và kiểm tra dedup/lookup.
9. **Edge cases:** null fields, empty strings, arrays, NaN/signed zeros nếu relevant.
10. **Kế thừa:** Parent vs Child và Child vs Parent để bắt symmetry.
11. **Mutation:** thử sửa state/element/referent để biết key có ổn định không.
12. **Concurrency/lifecycle:** nếu domain yêu cầu, kiểm thử tính ổn định dưới các điều kiện thực tế.

**Không đặt điều kiện** “hai unequal objects phải khác hash”. Đây không phải yêu cầu của Java, và test như vậy sẽ thất bại trên những collisions hoàn toàn hợp lệ.

### 28.1. Chương trình tự kiểm thử không cần JUnit

Lưu **`EqualityContractCheckDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class EqualityContractCheckDemo {
    record Key(String code, int number) {
        Key {
            Objects.requireNonNull(code, "code");
        }
    }

    static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        Key a = new Key("A", 1);
        Key b = new Key("A", 1);
        Key c = new Key("A", 1);
        Key different = new Key("A", 2);

        check(a.equals(a), "reflexive");
        check(a.equals(b) && b.equals(a), "symmetric");
        check(a.equals(b) && b.equals(c) && a.equals(c),
                "transitive");
        check(!a.equals(null), "non-null");
        check(!a.equals(different), "different key");

        int hashBefore = a.hashCode();
        check(hashBefore == a.hashCode(), "consistent hash");
        check(a.hashCode() == b.hashCode(), "equal hash");

        Map<Key, String> map = new HashMap<>();
        map.put(a, "found");
        check("found".equals(map.get(b)), "map lookup");
        check("found".equals(map.get(c)), "map lookup third");

        System.out.println("all checks passed");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac EqualityContractCheckDemo.java
java EqualityContractCheckDemo
~~~

Output:

~~~text
all checks passed
~~~

Khác với Java `assert` thường bị **tắt mặc định** nếu không bật `-ea`, method `check` trong ví dụ luôn ném `AssertionError` nếu điều kiện false. Vì vậy lệnh `java EqualityContractCheckDemo` kiểm tra đúng những điều được viết, không phụ thuộc một VM flag.

**Đây là kiểm thử mẫu**, chưa tự chứng minh class đúng cho mọi inputs. Hãy thêm property-based tests hoặc thư viện như EqualsVerifier (khi dự án đã có dependency phù hợp), đặc biệt với class hierarchy và fields phức tạp.

## 29. Code review checklist: trước khi override

Trước khi merge một class định nghĩa `equals`/`hashCode`, trả lời:

1. **Class là value object hay entity?** Domain equality là gì?
2. **Có cần override `Object.equals` không?** Nếu identity semantics đã đúng, không bắt buộc override.
3. **Method có đúng signature `public boolean equals(Object)` và `@Override` không?**
4. **Có xử lý `other == null` và incompatible types bằng false không?**
5. **Có bảo vệ tính phản xạ, đối xứng, bắc cầu, nhất quán không?**
6. **Có inheritance khiến subclasses thêm equality state không?**
7. **`instanceof` hay `getClass` có phù hợp domain và proxies/framework không?**
8. **Những fields nào tham gia equality?** Tất cả có hợp đồng ổn định không?
9. **`hashCode` có dùng dữ liệu nhất quán với `equals` không?**
10. **Có chấp nhận collisions nhưng không làm mọi keys collision vô cớ không?**
11. **Các fields có mutable không?** Object có được dùng như hash key sau mutation không?
12. **Có nested mutable arrays/lists không?** Cần Arrays.equals/hashCode/defensive copy?
13. **Có cyclic reference graph không?** Tránh recursive equals/hashCode vô hạn.
14. **Có null fields, NaN, signed zeros, BigDecimal scale không?**
15. **Có được truy cập đồng thời không?** State stable/visibility?
16. **Có tests equal pairs, unequal pairs, symmetry, transitivity và map/set lookup không?**
17. **Có cần toString không?** toString không thuộc equality contract, nhưng không nên rò rỉ secrets/duyệt graph vô hạn.
18. **Có tài liệu công bố chính xác equality semantics cho client không?**

## 30. Những hiểu nhầm phổ biến

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “`==` và `equals` đều so contents.” | Với references, `==` so identity; `equals` theo implementation. |
| “Không override thì `equals` so tất cả fields.” | `Object.equals` mặc định so identity. |
| “Chỉ cần override `equals`.” | Nếu logical equality mới khác Object, thông thường phải override `hashCode` tương ứng. |
| “Hai objects equal có thể hash khác.” | Không; equal→same-hash là yêu cầu bắt buộc. |
| “Hai objects hash giống thì chắc equal.” | Không; collisions hợp lệ. |
| “Hash code là địa chỉ bộ nhớ.” | Không có bảo đảm API như vậy. |
| “Hash code phải unique.” | Không; chỉ có miền số nguyên 32 bit. |
| “Hash code giống giữa các lần chạy.” | Không phải hợp đồng chung. |
| “`equals(StudentKey)` override `Object.equals`.” | Không; là overload khác chữ ký. |
| “Dùng `==` để so String fields.” | Dùng `String.equals`/`Objects.equals` cho logical equality. |
| “`instanceof` luôn an toàn khi superclass mở rộng.” | Subclass equality có thể phá symmetry. |
| “`getClass` luôn là lựa chọn duy nhất đúng.” | Exact-class policy cũng phải phù hợp domain/proxies. |
| “`final` field nào cũng deep immutable.” | Final reference vẫn có thể trỏ mutable object. |
| “Key mutable dùng trong HashMap không vấn đề.” | Đổi fields tham gia hash/equality có thể làm lookup thất bại. |
| “HashMap sẽ tự rehash entry khi key đổi.” | Không có contract tự di chuyển entry theo mutation của key. |
| “HashSet lưu hai objects khác identity thì luôn size 2.” | Nếu objects equal về giá trị, set có thể chỉ một. |
| “Record tự deep-copy arrays.” | Không; arrays components cần defensive copy khi muốn value semantics. |
| “Array.equals so nội dung.” | Array instance equals dùng identity; dùng Arrays.equals/deepEquals. |
| “List.copyOf deep copy elements.” | Không; mutable elements vẫn có thể shared. |
| “`BigDecimal.compareTo()==0` tương đương equals.” | Không với các scales khác nhau. |
| “TreeSet luôn cùng khái niệm trùng với HashSet.” | Sorted set dùng ordering/comparator; cần consistent-with-equals. |
| “Approximate floating equality luôn hợp lệ làm Object.equals.” | Có thể phá tính bắc cầu. |
| “NaN == NaN true.” | Với primitive double, false. |
| “`+0.0` và `-0.0` không khác gì trong hash.” | Phải nhất quán với equality strategy của double. |
| “Objects.hash mọi collection/array đều deep.” | Không; phụ thuộc equals/hashCode của field và varargs semantics. |
| “Bất kỳ chuỗi bidirectional references đều so sâu được.” | Có thể gây recursion vô hạn trong equals/hashCode. |
| “IdentityHashMap sửa được mọi key sai.” | Nó đổi equality semantics thành identity, không sửa domain key. |
| “`hashCode` là cryptographic checksum.” | Không phù hợp security/integrity. |
| “Thread-safe map làm mutable key an toàn.” | Vẫn phải giữ equality/hash ổn định. |

## 31. Câu hỏi ôn tập có lời giải

**Câu 1.** Hai `new Box(7)` objects không override equals sẽ equal không?  
**Đáp án:** Không. Object.equals mặc định identity.

**Câu 2.** Hai references `a` và `b` trỏ cùng object thì `a == b` bằng gì?  
**Đáp án:** True, vì cùng reference identity.

**Câu 3.** `new String("A").equals(new String("A"))` bằng gì?  
**Đáp án:** True vì String so nội dung.

**Câu 4.** `a.equals(a)` phải đúng tính chất nào?  
**Đáp án:** Reflexivity; true với a non-null.

**Câu 5.** `a.equals(b)` true nhưng `b.equals(a)` false vi phạm gì?  
**Đáp án:** Symmetry.

**Câu 6.** a=b, b=c nhưng a≠c vi phạm gì?  
**Đáp án:** Transitivity.

**Câu 7.** `a.equals(null)` phải trả gì nếu a non-null?  
**Đáp án:** False.

**Câu 8.** `equals` có thể thay đổi kết quả nếu fields tham gia equality bị mutate?  
**Đáp án:** Có; consistency chỉ yêu cầu cùng kết quả khi thông tin tham gia equality không đổi. Nhưng tránh dùng key mutable trong hash collections.

**Câu 9.** Nếu `a.equals(b)` true, `a.hashCode()==b.hashCode()` phải là gì?  
**Đáp án:** True.

**Câu 10.** Nếu `a.hashCode()==b.hashCode()`, có suy ra `a.equals(b)` không?  
**Đáp án:** Không, vì collision.

**Câu 11.** Có hợp lệ nếu mọi object trong một class luôn trả hash code 1?  
**Đáp án:** Có thể đúng contract, nhưng rất kém hiệu năng trong hash collections.

**Câu 12.** Vì sao chỉ override equals mà giữ Object.hashCode nguy hiểm?  
**Đáp án:** Hai objects equal theo fields có thể hash khác nhau, vi phạm equal→same-hash.

**Câu 13.** `equals(StudentKey)` có override Object.equals không?  
**Đáp án:** Không. Phải dùng `equals(Object)` và `@Override`.

**Câu 14.** HashSet thêm hai StudentKey khác identity nhưng cùng fields sẽ có mấy phần tử nếu equals/hash đúng?  
**Đáp án:** Một đại diện cho nhóm equal.

**Câu 15.** Vì sao sửa field tham gia hash sau `map.put(key,value)` dễ gây lookup lỗi?  
**Đáp án:** Collection đã tổ chức entry theo hash trước; lookup dùng hash mới có thể không tìm đúng entry.

**Câu 16.** `final List<String> tags` đã đủ ngăn mutable key không?  
**Đáp án:** Không. List object vẫn có thể bị mutate nếu lộ reference.

**Câu 17.** `getClass` check làm gì trong equals?  
**Đáp án:** Đòi exact runtime class giống nhau; loại bỏ equality cross-subtype.

**Câu 18.** `instanceof Point` trong Point.equals có thể gây vấn đề gì khi ColorPoint thêm color?  
**Đáp án:** Subclass equality có thể phá symmetry/transitivity hoặc hash contract.

**Câu 19.** `Objects.equals(a,b)` hữu ích khi nào?  
**Đáp án:** Khi fields có thể null; so null-safe.

**Câu 20.** `int[].equals(int[])` so contents không?  
**Đáp án:** Không. Array instance equals so identity.

**Câu 21.** Muốn hai `int[]` equal theo contents và hash nhất quán thì dùng gì?  
**Đáp án:** `Arrays.equals` cùng `Arrays.hashCode`.

**Câu 22.** Record có `int[]` component tự deep immutable không?  
**Đáp án:** Không; cần copy input/output nếu muốn ngăn aliasing.

**Câu 23.** Vì sao nested arrays có thể cần `Arrays.deepEquals`?  
**Đáp án:** `Arrays.equals` trên array ngoài sẽ dùng equality của nested array elements (identity), không so sâu nội dung.

**Câu 24.** Hai `BigDecimal("2.0")` và `BigDecimal("2.00")` equals nhau không?  
**Đáp án:** Không; scale khác.

**Câu 25.** Hai BigDecimals đó có `compareTo()==0` không?  
**Đáp án:** Có; cùng numeric value.

**Câu 26.** Vì sao HashSet và TreeSet có thể có size khác nhau với hai BigDecimals trên?  
**Đáp án:** HashSet dựa equals/hash; TreeSet dùng comparison tương đương 0.

**Câu 27.** `Double.NaN == Double.NaN` là gì với primitives?  
**Đáp án:** False.

**Câu 28.** Vì sao dùng primitive `==` cho double fields trong equals cần cẩn trọng?  
**Đáp án:** NaN/signed zeros có thể phá reflexivity hoặc tương thích hash tùy triển khai.

**Câu 29.** So gần đúng `|a-b|<epsilon` có phù hợp Object.equals không?  
**Đáp án:** Thường không, vì không bảo đảm transitivity.

**Câu 30.** Hai objects A và B trỏ nhau, nếu equals/hash duyệt mọi reference recursively thì có thể gặp gì?  
**Đáp án:** Đệ quy không dừng/StackOverflowError; cần domain identity hoặc thuật toán graph-aware.

**Câu 31.** Khi nào nên dùng IdentityHashMap?  
**Đáp án:** Khi semantics chính là object identity, như một số graph algorithms; không dùng nó thay HashMap cho logical value keys.

**Câu 32.** `Objects.hashCode(null)` trả gì?  
**Đáp án:** Trả 0 theo API; hữu ích cho null-safe hashing.

**Câu 33.** `Objects.hash(name, age)` có cần cùng danh sách fields với equals không?  
**Đáp án:** Phải bảo đảm equal objects có hash bằng nhau; thường dùng cùng equality-relevant fields.

**Câu 34.** Hash code nên có giá trị cố định xuyên các lần chạy chương trình không?  
**Đáp án:** Không phải yêu cầu chung của Object.hashCode; đừng dùng làm persistent identifier.

**Câu 35.** Nếu hai objects không equal nhưng cùng hash, HashMap có lưu hai keys riêng không?  
**Đáp án:** Có, nếu equals/hash contract của keys đúng; collision được xử lý theo map semantics.

**Câu 36.** Unit test nào đặc biệt cần khi kế thừa và override equals?  
**Đáp án:** Test cả `parent.equals(child)` và `child.equals(parent)`, cùng transitivity/hash consistency.

## 32. Tài liệu tham khảo

- Java Platform API Java SE 17, [`Object.equals(Object)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): hợp đồng reflexive/symmetric/transitive/consistent/non-null.
- Java Platform API Java SE 17, [`Object.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()): hợp đồng equal→same hash và các giới hạn.
- Java Platform API, [`Objects.equals(Object,Object)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)): so sánh null-safe.
- Java Platform API, [`Objects.hash(Object...)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#hash(java.lang.Object...)): tính hash từ nhiều arguments.
- Java Platform API, [`HashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): map dựa hashing và keys.
- Java Platform API, [`HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): set dựa hashing và uniqueness.
- Java Platform API, [`IdentityHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): reference identity semantics.
- Java Platform API, [`Arrays.equals`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): content equality của arrays.
- Java Platform API, [`Arrays.deepEquals`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#deepEquals(java.lang.Object%5B%5D,java.lang.Object%5B%5D)): nested arrays.
- Java Platform API, [`BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): scale-sensitive equals và compareTo.
- Java Language Specification Java SE 17, [`8.10 — Record Classes`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record equality/hash semantics.
- Java Language Specification, [`15.21 — Equality Operators`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21): `==` đối với primitives/references.
- Java Platform API, [`Set`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): tập hợp và equality.
- Java Platform API, [`SortedSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html): ordering và consistency với equals.

## Kết luận

`equals(Object)` định nghĩa **hai objects được coi là bằng nhau theo ý nghĩa nào**. `hashCode()` cung cấp giá trị hash phù hợp cho các cấu trúc dựa trên hashing. Hợp đồng quan trọng nhất: **nếu `a.equals(b)` là true thì `a.hashCode() == b.hashCode()` phải true**; hash bằng nhau **không** chứng minh objects bằng nhau.

Một implementation tốt giữ năm tính chất của `equals`, so đúng fields của domain, xử lý null và inheritance, dùng một chiến lược hash nhất quán, và tránh mutable key state. Với arrays hãy sử dụng `Arrays.equals/hashCode` phù hợp; với records hãy nhớ shallow immutability; với BigDecimal đừng nhầm equality với numeric comparison.

Khi thiết kế class dùng làm **key trong `HashMap`** hoặc **element trong `HashSet`**, ưu tiên immutable value objects hoặc records có components an toàn, viết tests reflexive/symmetric/transitive/hash contract và các trường hợp edge. Đừng dùng hash code làm identity duy nhất hay kỳ vọng GC/JVM sẽ tự sửa những keys bị mutate. **Bình đẳng hợp lệ là hợp đồng của kiểu, không phải may rủi của một lần so sánh.**
