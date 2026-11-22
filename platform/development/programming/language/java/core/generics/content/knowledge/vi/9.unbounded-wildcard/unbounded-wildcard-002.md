# Vì sao `List<?>` khác với `List<Object>` trong Java Generics?

Hai khai báo sau trông giống nhau vì mọi đối tượng Java đều có thể được xem như `Object`, nhưng chúng diễn đạt **hai hợp đồng kiểu hoàn toàn khác nhau**:

~~~java
List<?> unknownElements;
List<Object> objectElements;
~~~

- **`List<?>`**: một danh sách có **một kiểu phần tử cụ thể nào đó nhưng chưa biết kiểu ấy là gì**. Nó có thể là `List<String>`, `List<Integer>`, `List<Object>` hoặc một kiểu tham số hóa khác. Ta có thể đọc phần tử dưới dạng `Object`, nhưng không được tự ý thêm phần tử không phải `null` vì không biết danh sách thật chấp nhận kiểu gì.
- **`List<Object>`**: một danh sách có **đối số kiểu chính xác là `Object`**. Ta có thể thêm `String`, `Integer`, `Boolean` và bất kỳ giá trị tham chiếu nào khác vì tất cả đều gán được cho `Object`. Tuy nhiên, không thể gán trực tiếp `List<String>` hoặc `List<Integer>` vào biến `List<Object>`.

Điểm phân biệt cốt lõi: **“đọc được một phần tử như `Object`” không đồng nghĩa “được phép ghi mọi `Object` vào danh sách”.** Kiểu ở phía đọc và hợp đồng ghi là hai vấn đề khác nhau.

## 1. Hiểu chính xác dấu `?` và tên `Object`

Trong `List<?>`, dấu `?` là **unbounded wildcard**: compiler biết đây là một `List` có tham số kiểu, nhưng không biết tham số đó là kiểu nào. Ví dụ:

~~~java
List<String> names = new ArrayList<>();
List<Integer> ages = new ArrayList<>();

List<?> first = names; // Hợp lệ.
List<?> second = ages; // Hợp lệ.
~~~

Mỗi danh sách vẫn giữ đối số kiểu ban đầu. Wildcard **không chuyển** `List<String>` thành `List<Object>` và không thay đổi dữ liệu của collection. Một biến `List<?>` chỉ cung cấp **góc nhìn có khả năng sử dụng hạn chế** lên collection.

Trong `List<Object>`, `Object` là một **đối số kiểu xác định**, giống như `String` hoặc `Integer` cũng là các đối số kiểu xác định. Vì generic class/interface thông thường trong Java là **invariant** theo đối số kiểu, phép gán sau bị từ chối:

~~~java
List<String> names = new ArrayList<>();
List<Object> objects = names; // LỖI BIÊN DỊCH.
~~~

Đây là ví dụ **cố ý không biên dịch**. Lý do: nếu phép gán được phép, ta có thể gọi `objects.add(123)`, từ đó đưa `Integer` vào danh sách đang hứa chỉ chứa `String`.

Câu “mọi `String` đều là `Object`” vẫn đúng; điều không đúng là suy ra “mọi `List<String>` đều là `List<Object>`”.

## 2. So sánh trực tiếp về phép gán, đọc và ghi

| Đặc điểm | `List<?>` | `List<Object>` |
| --- | --- | --- |
| Ý nghĩa | Danh sách có **kiểu phần tử chưa biết** | Danh sách có kiểu phần tử **chính xác là `Object`** |
| Nhận `List<String>` | Có | Không |
| Nhận `List<Integer>` | Có | Không |
| Nhận `List<Object>` | Có | Có |
| Kiểu tĩnh của `get(index)` khi gán thông thường | `Object` | `Object` |
| `add("Java")` | Không biên dịch | Biên dịch |
| `add(123)` | Không biên dịch | Biên dịch (autoboxing thành `Integer`) |
| `add(new Object())` | Không biên dịch | Biên dịch |
| `add(null)` | Biên dịch; collection thật có thể từ chối lúc chạy | Biên dịch; collection thật có thể từ chối lúc chạy |
| `size()`, `isEmpty()`, `contains(Object)` | Dùng được | Dùng được |
| `clear()`, `remove(index)` | Biên dịch; khả năng thực thi tùy collection | Biên dịch; khả năng thực thi tùy collection |
| Dùng làm tham số nhận danh sách bất kỳ | Thường phù hợp | Chỉ nhận danh sách có đối số kiểu `Object` |

Bảng so sánh nói về **kiểm tra kiểu tại thời điểm biên dịch**. Dù một lời gọi `add` hay `clear` biên dịch, danh sách thật có thể không cho sửa (ví dụ `List.of(...)`) và ném `UnsupportedOperationException` lúc chạy. Một số collection cũng không cho chứa `null`.

### Vì sao cả hai đều trả `Object` khi đọc?

`Object` là một supertype của tất cả các kiểu tham chiếu Java. Với `List<?>`, phần tử thực có thể là `String`, `Integer` hay bất kỳ kiểu nào khác nên compiler chỉ bảo đảm mức chung là `Object`. Với `List<Object>`, `Object` chính là kiểu phần tử được khai báo.

~~~java
List<String> names = new ArrayList<>(List.of("An"));
List<?> unknown = names;

Object a = unknown.get(0); // Hợp lệ.
String b = names.get(0);   // Hợp lệ nhờ tham chiếu gốc List<String>.

// String c = unknown.get(0); // LỖI: chỉ bảo đảm Object.
~~~

Giá trị vật lý vẫn là cùng đối tượng `String`; chỉ **kiểu tĩnh mà compiler cam kết** khác nhau. Có thể kiểm tra `instanceof` hoặc ép kiểu có chủ đích, nhưng khi ấy phải xử lý trường hợp kiểu thực không phù hợp.

## 3. Chương trình chạy được: một API nhận mọi danh sách, một danh sách chứa nhiều loại đối tượng

Tạo tệp **`UnknownVsObjectDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class UnknownVsObjectDemo {
    private static void printItems(List<?> items) {
        for (Object item : items) {
            System.out.println("item: " + item);
        }
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Ada", "Lin"));
        List<Integer> ids = new ArrayList<>(List.of(7, 9));

        List<?> unknown = names;
        List<Object> objects = new ArrayList<>();

        objects.add("Ada");
        objects.add(7);
        objects.add(true);

        System.out.println("first = " + unknown.get(0));
        System.out.println("objects = " + objects);

        printItems(names);
        printItems(ids);

        unknown = ids;
        System.out.println("new first = " + unknown.get(0));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac UnknownVsObjectDemo.java
java UnknownVsObjectDemo
~~~

Stdout chính xác:

~~~text
first = Ada
objects = [Ada, 7, true]
item: Ada
item: Lin
item: 7
item: 9
new first = 7
~~~

Phân tích kết quả:

1. `unknown` ban đầu nhìn vào `List<String>`. Khi gọi `get(0)`, kiểu tĩnh là `Object` nhưng đối tượng thực là chuỗi `"Ada"`.
2. `objects` thực sự là `List<Object>`. Nó được phép chứa đồng thời một chuỗi, một `Integer` và một `Boolean`.
3. `printItems(List<?>)` nhận cả `List<String>` và `List<Integer>` mà không cần raw type hay unchecked cast. Vì chỉ đọc và in phần tử như `Object` nên nó không cần biết đối số kiểu cụ thể.
4. Sau khi gán `unknown = ids`, biến wildcard nhìn vào danh sách số nguyên. Thao tác này hợp lệ vì `List<?>` có thể tham chiếu nhiều kiểu danh sách khác nhau **ở các thời điểm khác nhau**.

Lưu ý: mỗi đối tượng collection vẫn có một kiểu phần tử phù hợp với tham chiếu gốc trong chương trình. Việc đổi biến `unknown` sang danh sách khác **không biến một danh sách thành loại danh sách khác**.

## 4. Vì sao `List<?>` không thêm được `Object`?

Xét:

~~~java
List<String> words = new ArrayList<>(List.of("one", "two"));
List<?> unknown = words;

Object newItem = Integer.valueOf(3);

// unknown.add(newItem); // LỖI BIÊN DỊCH.
// unknown.add("three"); // CŨNG LỖI BIÊN DỊCH.
~~~

Compiler nhìn thấy `List<?>` và hiểu rằng wildcard đại diện cho **một kiểu cụ thể chưa biết**. Có thể kiểu ấy là `String`, như ở ví dụ; cũng có thể là `Integer`. Nếu nhận bất kỳ `Object` nào, Java sẽ vô tình cho phép đưa `Integer` vào `List<String>`. Nếu chỉ cho thêm `String`, Java lại có thể làm sai trong trường hợp biến đang trỏ vào `List<Integer>`.

Do đó, **biến `List<?>` không cho phép thêm một giá trị có kiểu tham chiếu cụ thể**. Điều này khác hẳn `List<Object>`:

~~~java
List<Object> objects = new ArrayList<>();
objects.add("three");
objects.add(Integer.valueOf(3));
objects.add(new Object()); // Cả ba lời gọi đều hợp lệ.
~~~

### Trường hợp đặc biệt: `null`

~~~java
List<String> words = new ArrayList<>();
List<?> unknown = words;

unknown.add(null); // Biên dịch được.
System.out.println(words); // [null]
~~~

`null` là giá trị tương thích với mọi kiểu tham chiếu, nên compiler cho phép thêm qua wildcard. Tuy nhiên, điều này **không có nghĩa mọi collection chấp nhận `null`**: ví dụ danh sách từ `List.of(...)` không cho thêm phần tử, còn nhiều collection cấm `null`. Mã có thể biên dịch mà vẫn ném ngoại lệ khi chạy.

Không nên lấy khả năng `add(null)` làm lý do dùng `List<?>` để chứa dữ liệu. Ý nghĩa chính của wildcard là không giả định sai về kiểu phần tử.

## 5. `List<?>` không phải `List<Object>`, cũng không phải raw `List`

Ba dạng khai báo dễ nhầm:

~~~java
List<?> unknown;        // Có generic; kiểu phần tử tồn tại nhưng không xác định.
List<Object> objects;   // Có generic; đối số kiểu được xác định là Object.
List raw;               // Raw type; bỏ qua tham số generic trong khai báo.
~~~

Với `List<?>`, compiler giữ được thông tin “đây là một danh sách với một kiểu phần tử nhất quán nhưng chưa biết”. Vì vậy, nó ngăn một lời gọi `add(42)` không an toàn.

Với raw `List`, một số phép ghi sẽ **biên dịch kèm cảnh báo unchecked**, có thể gây lỗi lúc đọc:

~~~java
List<String> names = new ArrayList<>();
List raw = names;
raw.add(42); // Cảnh báo unchecked: có thể làm nhiễm kiểu List<String>.
~~~

Đây là **đoạn mã minh họa nguy cơ**, không phải thiết kế được khuyến nghị. Trường hợp `names.get(0)` được nhận vào biến `String`, runtime có thể ném `ClassCastException` vì phần tử thực là `Integer`. Dùng `List<?>` để khai báo tham số chỉ đọc là cách an toàn hơn nhiều so với raw `List`.

Không nên coi `List<?>` là “`List<Object>` viết gọn”; hai kiểu này có quyền ghi khác nhau. Cũng không nên coi wildcard là bỏ kiểm tra kiểu; mục tiêu của nó là **giữ kiểm tra kiểu mà không cần biết một đối số kiểu cụ thể**.

## 6. Khác biệt về thao tác ghi không đồng nghĩa với immutability

`List<?>` hạn chế kiểu của **giá trị mới** đưa vào danh sách; nó không phải một giao diện bất biến. Chẳng hạn, nếu backing list sửa được, `remove(int)`, `remove(Object)` và `clear()` vẫn có thể thay đổi nội dung qua alias wildcard. Trong khi đó, `List<Object>` còn được phép `add` một tham chiếu thuộc kiểu Object.

```java
List<String> words = new ArrayList<>(List.of("A", "B"));
List<?> unknown = words;
Object removed = unknown.remove(0);
System.out.println(removed + " -> " + words); // A -> [B]
```

Điểm khác giữa hai hợp đồng vẫn là **đối số kiểu chưa biết** so với **đối số kiểu Object chính xác**. Việc lời gọi `remove` biên dịch không bảo đảm luôn thành công: `List.of` không cho thay đổi, `Arrays.asList` có kích thước cố định, còn `ArrayList` hỗ trợ xóa. Đó là tính chất của implementation, không phải hệ quả của wildcard.

## 7. Wildcard capture: tại sao vẫn có thể hoán đổi hai phần tử trong `List<?>`?

Thoạt nhìn, nếu không biết kiểu `?`, ta không thể gọi `set(index, newValue)` với một `Object` bất kỳ. Nhưng ta có thể nhờ **một phương thức generic nắm bắt kiểu ẩn** và thao tác với những phần tử **đã lấy ra từ chính danh sách đó**.

Tạo tệp **`WildcardCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureDemo {
    static void swapFirstTwo(List<?> values) {
        if (values.size() < 2) {
            return;
        }
        swapCaptured(values, 0, 1);
    }

    private static <T> void swapCaptured(List<T> values, int i, int j) {
        T first = values.get(i);
        values.set(i, values.get(j));
        values.set(j, first);
    }

    public static void main(String[] args) {
        List<String> letters =
                new ArrayList<>(List.of("A", "B", "C"));
        List<Integer> numbers =
                new ArrayList<>(List.of(10, 20));

        swapFirstTwo(letters);
        swapFirstTwo(numbers);

        System.out.println(letters);
        System.out.println(numbers);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac WildcardCaptureDemo.java
java WildcardCaptureDemo
~~~

Stdout:

~~~text
[B, A, C]
[20, 10]
~~~

Giải thích từng bước:

1. `swapFirstTwo` nhận `List<?>` nên có thể được gọi với `List<String>` và `List<Integer>`.
2. Khi chuyển `values` tới `swapCaptured`, compiler dùng **capture conversion** để xem wildcard như một kiểu nhất quán tạm thời, ký hiệu ở phương thức đích là `T`.
3. Cả phần tử đọc ra và vị trí ghi trở lại đều có kiểu `T`. Vì vậy, thao tác hoán đổi **không tạo phần tử có kiểu khác** so với collection ban đầu.
4. Không có cast từ `Object` sang `String`, không có raw type, không cần `@SuppressWarnings("unchecked")`.

Thư viện chuẩn có sẵn `Collections.swap(List<?>, int, int)` với ý tưởng tương tự. Ví dụ này giúp thấy rõ: wildcard **không cấm mọi phép biến đổi**, mà cấm các phép ghi không chứng minh được an toàn kiểu.

## 8. API nên nhận `List<?>` khi nào, nên nhận `List<Object>` khi nào?

### 8.1. Chỉ cần xử lý phần tử như `Object`: chọn `List<?>`

Ví dụ phương thức đếm, duyệt/in, kiểm tra rỗng hoặc đăng log mà không cần biết kiểu phần tử:

~~~java
static void describe(List<?> items) {
    System.out.println("Count: " + items.size());
    for (Object item : items) {
        System.out.println(item);
    }
}
~~~

Đây là **phương thức minh họa**, cần đặt trong một class và import `java.util.List`. Nó nhận `List<String>`, `List<Integer>`, `List<Object>` và các kiểu danh sách khác.

Nếu thay tham số bằng `List<Object>`, caller truyền `List<String>` sẽ gặp lỗi compile-time dù thân phương thức chỉ đọc. Hợp đồng `List<Object>` đã **vô tình yêu cầu cụ thể hơn nhu cầu thật của API**.

### 8.2. Cần thêm những giá trị `Object` bất kỳ: chọn `List<Object>`

~~~java
static void appendMixedValues(List<Object> destination) {
    destination.add("created");
    destination.add(2026);
    destination.add(Boolean.TRUE);
}
~~~

Đây cũng là **phương thức cần đặt trong class**. Nó có quyền thêm giá trị thuộc nhiều loại khác nhau vì caller phải cung cấp chính xác một `List<Object>`:

~~~java
List<Object> destination = new ArrayList<>();
appendMixedValues(destination); // Hợp lệ.

// List<String> names = new ArrayList<>();
// appendMixedValues(names); // LỖI BIÊN DỊCH.
~~~

Nếu thay bằng `List<?>`, thân phương thức sẽ không được gọi `add("created")` vì không biết loại danh sách mà caller truyền vào.

### 8.3. Cần lưu mọi phần tử từ danh sách cụ thể vào một `List<Object>` mới

Do generic invariance, đoạn sau không hợp lệ:

~~~java
List<String> words = new ArrayList<>(List.of("A", "B"));
// List<Object> direct = words; // LỖI BIÊN DỊCH.
~~~

Nhưng bạn có thể **sao chép**:

~~~java
List<String> words = new ArrayList<>(List.of("A", "B"));
List<Object> copied = new ArrayList<>(words);

copied.add(42);               // Hợp lệ với danh sách mới.
System.out.println(words);    // [A, B]
System.out.println(copied);   // [A, B, 42]
~~~

Đây là **đoạn mã để đặt trong class**, có import `java.util.List` và `java.util.ArrayList`. Constructor `ArrayList` nhận `Collection<? extends E>`; với đích có `E = Object`, một `Collection<String>` cung cấp phần tử hợp lệ. Hai collection riêng biệt có thể chia sẻ **các đối tượng phần tử** nhưng không chia sẻ cấu trúc danh sách; thêm phần tử vào `copied` không thêm vào `words`.

Nếu cần “xem” bất kỳ danh sách nào thì dùng `List<?>`. Nếu thật sự cần **chứa trộn các loại đối tượng** dưới một kiểu phần tử rộng, tạo `List<Object>` rõ ràng.

## 9. Liên hệ với `? extends Object` và các generic khác

Giới hạn mặc định của unbounded wildcard là `Object` (với các kiểu tham chiếu). Trong những ngữ cảnh thông thường, `List<?>` mang ý nghĩa tương đương `List<? extends Object>`. Nhưng chúng **không tương đương `List<Object>`**.

~~~java
List<String> words = new ArrayList<>();

List<?> first = words;                 // Hợp lệ.
List<? extends Object> second = words; // Hợp lệ.
// List<Object> third = words;         // LỖI.
~~~

Sự khác nhau đến từ **wildcard cho phép nhiều đối số kiểu cụ thể** còn `Object` là một **đối số kiểu chính xác**.

Quy tắc cũng xuất hiện ở các generic khác:

~~~java
Set<String> names = new HashSet<>();
Set<?> unknownSet = names; // Hợp lệ.
// Set<Object> objectSet = names; // LỖI.

Map<String, Integer> scores = new HashMap<>();
Map<?, ?> unknownMap = scores; // Hợp lệ.
// Map<Object, Object> objectMap = scores; // LỖI.
~~~

Đây là **mã minh họa cần import `java.util.*` và đặt trong class**. `Map<?, ?>` cho phép duyệt entry dưới góc nhìn `Object` cho cả key và value, nhưng không cho tự ý thêm một cặp key/value mới với kiểu không xác định (trừ các trường hợp đặc biệt liên quan `null`). Quy tắc an toàn kiểu là cùng một cơ chế.

### Không thể overload chỉ bằng `List<?>` và `List<Object>`

Mặc dù hai kiểu có ý nghĩa khác nhau ở thời điểm biên dịch, ta **không được** viết đồng thời hai overload sau trong cùng class:

~~~java
void handle(List<?> values) {}
void handle(List<Object> values) {} // LỖI: name clash do same erasure.
~~~

Đây là **ví dụ cố ý không biên dịch**. Cả hai chữ ký đều bị xóa đối số generic thành cùng dạng `handle(List)` khi áp dụng **type erasure**. Như vậy, khác biệt trong khả năng gán/ghi của chúng là thật ở nguồn Java, nhưng không đủ để định danh hai overload ở bytecode.

### Kiểm tra kiểu với `instanceof`

`List<?>` là dạng dùng được trong phép kiểm tra `instanceof`, còn kiểm tra đối số `Object` cụ thể thì không:

~~~java
Object value = List.of("x", "y");

if (value instanceof List<?> items) {
    System.out.println(items.size());
}

// if (value instanceof List<Object>) { ... } // LỖI BIÊN DỊCH.
~~~

Đây là **mã minh họa cần import `java.util.List` và đặt trong class**. Runtime chỉ biết chắc đối tượng là `List`, không thể khẳng định đối số kiểu generic cụ thể của danh sách là `Object`.

## 10. Lỗi thường gặp và cách nhận diện

**Lỗi 1 — Cho rằng `List<?>` là viết tắt của `List<Object>`.** Sai: `List<?>` chấp nhận `List<String>`; `List<Object>` thì không. Phép gán và khả năng ghi khác nhau.

**Lỗi 2 — Dùng `List<Object>` làm tham số chỉ để in mọi danh sách.** Phương thức sẽ từ chối `List<String>` và `List<Integer>` vô ích. Nếu chỉ đọc như `Object`, dùng `List<?>`.

**Lỗi 3 — Nghĩ rằng vì `get()` trả `Object` nên `add(new Object())` phải hợp lệ.** Không đúng: đọc kiểu rộng không chứng minh danh sách thật chấp nhận thêm một `Object` bất kỳ.

**Lỗi 4 — Nghĩ `List<?>` là immutable.** Sai: các thao tác xóa, làm rỗng và hoán đổi qua generic helper có thể hợp lệ. Khả năng sửa phụ thuộc đối tượng collection thật.

**Lỗi 5 — Dùng raw `List` để “giải quyết” lỗi compiler.** Raw type có thể cho thêm sai phần tử với cảnh báo unchecked rồi gây `ClassCastException` về sau. Wildcard và tham số generic đúng mục đích an toàn hơn.

**Lỗi 6 — Ép kiểu `List<?>` thành `List<Object>` để gọi `add`.** Kiểu thực có thể là `List<String>`; unchecked cast có thể gây heap pollution. Không được xem cast là cách nâng cấp khả năng ghi hợp lệ.

**Lỗi 7 — Nhầm việc sao chép với gán tham chiếu.** `new ArrayList<Object>(aStringList)` tạo một collection mới, có thể thêm `Object` tùy ý. `List<Object> objects = aStringList` là phép gán cùng đối tượng nhưng sai kiểu, nên bị cấm.

## 11. Tự kiểm tra

Cho:

~~~java
List<String> names = new ArrayList<>(List.of("A", "B"));
List<?> unknown = names;
List<Object> objects = new ArrayList<>();
~~~

Xác định từng câu đúng/sai về **khả năng biên dịch**:

1. `Object x = unknown.get(0);`
2. `String s = unknown.get(0);`
3. `unknown.add("C");`
4. `unknown.add(null);`
5. `objects.add("C");`
6. `List<Object> direct = names;`
7. `List<?> other = objects;`
8. `objects.add(unknown.get(0));`
9. `unknown.clear();`
10. `List<Object> copy = new ArrayList<>(names);`

**Đáp án:**

| Câu | Biên dịch? | Giải thích |
| --- | --- | --- |
| 1 | Có | `get` từ wildcard có thể dùng như `Object` |
| 2 | Không | Kiểu tĩnh của `get` không bảo đảm là `String` |
| 3 | Không | Không biết kiểu phần tử ẩn phía sau wildcard |
| 4 | Có | `null` tương thích với mọi kiểu tham chiếu; runtime tùy collection |
| 5 | Có | `String` là subtype của `Object` |
| 6 | Không | Generic invariant; `List<String>` không phải `List<Object>` |
| 7 | Có | `List<?>` có thể nhận `List<Object>` |
| 8 | Có | Phần tử `unknown.get(0)` được dùng như `Object`, phù hợp đích |
| 9 | Có | `clear()` không đòi biết kiểu phần tử; runtime tùy collection |
| 10 | Có | Sao chép phần tử vào `ArrayList<Object>` mới |

Các biểu thức không biên dịch trong bài tập chỉ để phân tích, không đưa nguyên vào chương trình chạy.

## 12. Kết luận

**`List<?>` biểu thị “một danh sách thuộc một kiểu phần tử nào đó”**, còn **`List<Object>` biểu thị “một danh sách có đối số kiểu chính xác `Object`”**. Cả hai đều cho đọc phần tử dưới kiểu `Object` nhưng chỉ `List<Object>` cho phép ghi các giá trị `Object` bất kỳ. Unbounded wildcard chấp nhận nhiều danh sách khác nhau mà vẫn chặn những phép ghi không an toàn. Khi thiết kế API chỉ cần quan sát phần tử, `List<?>` thường là chữ ký chính xác; khi thật sự cần bổ sung nhiều loại đối tượng vào danh sách, dùng `List<Object>` hoặc tạo danh sách mới với đối số kiểu phù hợp.