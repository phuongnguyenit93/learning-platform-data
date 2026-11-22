# Viết `equals` với kiểm tra kiểu ngắn gọn bằng `instanceof` và đúng hợp đồng

## 1. Bài toán và cách viết hiện đại

Khi một lớp biểu diễn **giá trị logic** (ví dụ mã người dùng, mã giao dịch, tọa độ), ta thường muốn hai đối tượng khác tham chiếu vẫn được xem là bằng nhau nếu các trường quan trọng của chúng bằng nhau. Đó là mục đích của `equals(Object)`.

Từ Java 16, **pattern matching for `instanceof`** là tính năng chuẩn. Nó cho phép **kiểm tra kiểu và gắn biến đã ép kiểu trong cùng một biểu thức**:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof UserKey other)) return false;

    return id == other.id
            && tenant.equals(other.tenant);
}
```

Đây là **thân phương thức minh họa** cần đặt trong một lớp `UserKey` có các trường `id` và `tenant`. So với lối viết tách `instanceof` và ép kiểu, ta không còn cần dòng `UserKey other = (UserKey) obj;`. Quan trọng hơn, biến mẫu `other` chỉ được dùng trên đường đi mà việc kiểm tra kiểu đã thành công.

**Ngữ cảnh Java 14:** mẫu `instanceof` từng xuất hiện ở Java 14 dưới dạng preview, nhưng từ Java 16 đã trở thành cú pháp chính thức và **vẫn được dùng trong Java hiện đại**. Các ví dụ chạy được trong bài này sử dụng **Java 17+**, không dùng tùy chọn preview cũ.

Bài học không chỉ làm mã `equals` ngắn: **đúng hợp đồng** mới là mục tiêu chính. Cú pháp đẹp không tự bảo đảm tính đối xứng, bắc cầu, mã băm hoặc tính ổn định của dữ liệu.

## 2. Chữ ký đúng và ý nghĩa của phép kiểm tra kiểu

Chữ ký để ghi đè phương thức của `Object` phải là:

```java
@Override
public boolean equals(Object obj) {
    // Trả true hoặc false theo định nghĩa giá trị của lớp.
}
```

**Không nhầm với overload**:

```java
public boolean equals(UserKey other) {
    // Đây là overload, không phải override equals(Object)!
    return other != null && id == other.id;
}
```

Đoạn overload trên chỉ có ý nghĩa minh họa và cần được đặt trong lớp tương ứng. Nếu viết `equals(UserKey)` thay vì `equals(Object)`, các API như `HashSet`, `HashMap` vẫn có thể dùng `Object.equals(Object)` và cho kết quả khác mong đợi. Viết `@Override` trên phương thức thực sự cần ghi đè giúp trình biên dịch phát hiện sai chữ ký.

### 2.1. Ba dòng kiểm tra đầu tiên làm gì?

```java
if (this == obj) return true;
if (!(obj instanceof UserKey other)) return false;
// Từ đây có thể dùng other như UserKey.
```

- `this == obj`: hai tham chiếu trỏ chính một đối tượng; có thể trả `true` ngay, tránh so trường. Đây là **tối ưu tùy chọn**, không bắt buộc cho mọi `equals`.
- `obj instanceof UserKey other`: kiểm tra `obj` khác `null` và có kiểu runtime tương thích với `UserKey`; nếu đúng, liên kết biến `other` với đối tượng đã kiểm tra.
- Dấu `!` đảo kết quả. Khi mẫu **không khớp**, `return false` kết thúc phương thức.
- Ở các câu lệnh sau `if`, trình biên dịch biết rằng nếu chương trình còn tiếp tục thì mẫu **đã khớp**, nên `other` có phạm vi sử dụng (flow scoping).

Với `obj == null`, biểu thức `obj instanceof UserKey other` trả `false` và không ném `NullPointerException`. Vì vậy **không cần kiểm tra `obj != null` riêng** nếu dùng mẫu trên; `return false` đã xử lý trường hợp `null`.

Cũng có thể viết gọn hơn khi không cần nhánh `if`:

```java
@Override
public boolean equals(Object obj) {
    return obj instanceof UserKey other
            && id == other.id
            && tenant.equals(other.tenant);
}
```

Vế phải của `&&` được thực hiện **chỉ nếu mẫu khớp**; `other` đã được gán chắc chắn. Cả phiên bản `if` và phiên bản `&&` đều phù hợp với `final class UserKey` có `tenant` không nhận `null`. Chọn cách dễ đọc nhất với số trường và logic nghiệp vụ thực tế.

## 3. Hợp đồng chuẩn của `Object.equals`

Phương thức `equals` phải mô tả một **quan hệ tương đương** trên các tham chiếu khác `null`. Đây là các yêu cầu do `java.lang.Object` công bố, vẫn áp dụng cho Java hiện nay:

| Quy tắc | Ý nghĩa | Kiểm thử định hướng |
| --- | --- | --- |
| **Phản xạ (reflexive)** | Một đối tượng bằng chính nó | `x.equals(x) == true` |
| **Đối xứng (symmetric)** | Nếu `x` bằng `y` thì `y` cũng bằng `x` | `x.equals(y) == y.equals(x)` |
| **Bắc cầu (transitive)** | Nếu `x` bằng `y` và `y` bằng `z` thì `x` phải bằng `z` | Kiểm tra ba đối tượng cùng lớp |
| **Nhất quán (consistent)** | Khi dữ liệu liên quan không đổi, kết quả các lần gọi phải ổn định | Gọi lặp lại `equals` |
| **Không bằng `null`** | Đối tượng khác `null` không thể bằng `null` | `x.equals(null) == false` |

Ngoài các quy tắc trên, lớp ghi đè `equals` **thường phải ghi đè `hashCode` tương thích**:

> Nếu `a.equals(b)` đúng thì bắt buộc `a.hashCode() == b.hashCode()`.

Chiều ngược lại không được bảo đảm: hai đối tượng khác nhau có thể cùng mã băm. `HashSet` và `HashMap` dựa vào cả `hashCode` và `equals` để nhận diện giá trị/khóa.

Lưu ý quan trọng: `instanceof` chỉ xác nhận **kiểu của đối số**; nó không kiểm tra những quy tắc trên. Trách nhiệm chọn trường so sánh, thiết kế kiểu và duy trì dữ liệu nhất quán vẫn thuộc về tác giả lớp.

## 4. Chọn trường so sánh và thao tác theo kiểu dữ liệu

Sau kiểm tra kiểu, `equals` cần so sánh **đúng tất cả thuộc tính quyết định danh tính giá trị**.

| Loại trường | Cách so thường phù hợp | Ghi chú |
| --- | --- | --- |
| `int`, `long`, `boolean`, `char` | `==` | So trực tiếp giá trị nguyên thủy |
| `String` không `null` | `a.equals(b)` | Nên bảo đảm không `null` tại constructor |
| `String` hoặc tham chiếu có thể `null` | `Objects.equals(a, b)` | Hai `null` được xem bằng nhau, không tự ném lỗi |
| Một kiểu giá trị khác | Dùng `equals` phù hợp của kiểu đó | Kiểm tra kiểu thành phần có hợp đồng ổn định |
| `float` hoặc `double` | `Float.compare(a, b) == 0` hoặc `Double.compare(a, b) == 0` | Xử lý `NaN` và `+0.0/-0.0` nhất quán với wrapper |
| Mảng một chiều như `byte[]` | `Arrays.equals(a, b)` nếu ý nghĩa là so phần tử | Kết hợp `Arrays.hashCode`; cân nhắc sao chép phòng vệ |
| Mảng lồng nhau | Cân nhắc `Arrays.deepEquals` theo loại dữ liệu và yêu cầu | Đi kèm `Arrays.deepHashCode` khi cần so sâu |

**Hai điều cần tránh:**

1. `a == b` với trường `String` hoặc đối tượng tham chiếu thông thường chỉ so **cùng tham chiếu**, không nhất thiết so giá trị.
2. `Objects.equals(byteArrayA, byteArrayB)` không so nội dung mảng vì mảng không ghi đè `Object.equals`. Nếu cần so byte, dùng `Arrays.equals`.

### 4.1. Số thực: vì sao không tùy tiện dùng `==`?

`Double.NaN == Double.NaN` là `false`, nhưng `Double.compare(Double.NaN, Double.NaN) == 0` là `true`. Mặt khác, `+0.0 == -0.0` là `true` nhưng `Double.compare(+0.0, -0.0) == 0` là `false`.

Nếu chỉ có một trường `double` và muốn tuân theo ngữ nghĩa `Double.equals`, nên dùng cặp:

```java
@Override
public boolean equals(Object obj) {
    return obj instanceof Measurement other
            && Double.compare(value, other.value) == 0;
}

@Override
public int hashCode() {
    return Double.hashCode(value);
}
```

Đây là **hai phương thức minh họa** thuộc một lớp `Measurement` có trường `double value`. `Double.hashCode` dùng ngữ nghĩa phù hợp với `Double.compare` trong những trường hợp đặc biệt.

### 4.2. Dữ liệu thay đổi được và khóa bảng băm

Nếu trường tham gia `equals/hashCode` thay đổi sau khi đối tượng đã được thêm vào `HashSet` hoặc làm khóa `HashMap`, thao tác tìm kiếm có thể không còn nhận diện đúng phần tử. Vì vậy:

- Ưu tiên các trường `final` và **kiểu thành phần bất biến**.
- Tránh để bên ngoài sửa được mảng hoặc danh sách giữ bên trong đối tượng bằng cách sử dụng **defensive copy** khi thích hợp.
- Đừng coi từ khóa `final` trên tham chiếu là bằng chứng nội dung đối tượng tham chiếu bất biến.
- Với ID nghiệp vụ, xác định rõ các trường nào thực sự tạo ra danh tính; đừng vô tình bỏ sót một trường ở `equals` hoặc thêm trường không tương ứng vào `hashCode`.

## 5. Ví dụ Java 17+ đầy đủ: `equals` ngắn và đúng hợp đồng

Lưu chương trình sau vào tệp **`EqualsPatternDemo.java`**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class EqualsPatternDemo {

    static final class UserKey {
        private final String tenant;
        private final long id;

        UserKey(String tenant, long id) {
            this.tenant = Objects.requireNonNull(tenant, "tenant");
            this.id = id;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof UserKey other)) {
                return false;
            }
            return id == other.id && tenant.equals(other.tenant);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenant, id);
        }
    }

    static final class TextTag {
        private final String text;

        TextTag(String text) {
            this.text = text;
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof TextTag other
                    && Objects.equals(text, other.text);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(text);
        }
    }

    static final class Measurement {
        private final double value;

        Measurement(double value) {
            this.value = value;
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof Measurement other
                    && Double.compare(value, other.value) == 0;
        }

        @Override
        public int hashCode() {
            return Double.hashCode(value);
        }
    }

    static final class ByteSequence {
        private final byte[] bytes;

        ByteSequence(byte[] bytes) {
            this.bytes = Objects.requireNonNull(bytes).clone();
        }

        byte[] bytes() {
            return bytes.clone();
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof ByteSequence other
                    && Arrays.equals(bytes, other.bytes);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(bytes);
        }
    }

    record Point(int x, int y) {}

    public static void main(String[] args) {
        UserKey a = new UserKey("acme", 7L);
        UserKey b = new UserKey(new String("acme"), 7L);
        UserKey c = new UserKey("acme", 7L);
        UserKey different = new UserKey("acme", 8L);

        System.out.println("sameReference=" + (a == b));
        System.out.println("equalValues=" + a.equals(b));
        System.out.println("reflexive=" + a.equals(a));
        System.out.println("symmetric=" +
                (a.equals(b) && b.equals(a)));
        System.out.println("transitive=" +
                (a.equals(b) && b.equals(c) && a.equals(c)));
        System.out.println("null=" + a.equals(null));
        System.out.println("differentType=" + a.equals("acme"));
        System.out.println("differentField=" + a.equals(different));
        System.out.println("sameHash=" +
                (a.hashCode() == b.hashCode()));

        Set<UserKey> keys = new HashSet<>(
                List.of(a, b, c, different));
        System.out.println("setSize=" + keys.size());

        System.out.println("nullableNulls=" +
                new TextTag(null).equals(new TextTag(null)));
        System.out.println("nullableDifferent=" +
                new TextTag(null).equals(new TextTag("tag")));

        System.out.println("nanEqual=" +
                new Measurement(Double.NaN)
                        .equals(new Measurement(Double.NaN)));
        System.out.println("signedZeroEqual=" +
                new Measurement(+0.0)
                        .equals(new Measurement(-0.0)));

        byte[] source = {1, 2};
        ByteSequence bytesA = new ByteSequence(source);
        ByteSequence bytesB = new ByteSequence(new byte[] {1, 2});
        source[0] = 9;
        byte[] exposed = bytesA.bytes();
        exposed[1] = 9;

        System.out.println("arrayContentEqual=" +
                bytesA.equals(bytesB));
        System.out.println("arrayHashEqual=" +
                (bytesA.hashCode() == bytesB.hashCode()));

        System.out.println("recordAutoEqual=" +
                new Point(1, 2).equals(new Point(1, 2)));
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn; nếu muốn kiểm tra biên dịch đúng với mức ngôn ngữ Java 17, dùng `--release 17`:

```bash
javac --release 17 EqualsPatternDemo.java
java EqualsPatternDemo
```

**Đầu ra chính xác:**

```text
sameReference=false
equalValues=true
reflexive=true
symmetric=true
transitive=true
null=false
differentType=false
differentField=false
sameHash=true
setSize=2
nullableNulls=true
nullableDifferent=false
nanEqual=true
signedZeroEqual=false
arrayContentEqual=true
arrayHashEqual=true
recordAutoEqual=true
```

### Phân tích kết quả

1. `a == b` là `false` vì hai đối tượng `UserKey` được tạo riêng. `a.equals(b)` lại `true` vì `id` bằng nhau và `String.equals` so theo nội dung `tenant`.
2. Các dòng `reflexive`, `symmetric` và `transitive` cùng trả `true`. Chúng minh họa **một vài kiểm thử hợp đồng**, không phải chứng minh hình thức cho mọi giá trị có thể.
3. `a.equals(null)` trả `false` vì mẫu `instanceof` không khớp `null`. `a.equals("acme")` cũng sai do đối số không phải `UserKey`. Không ném `ClassCastException`.
4. `different` chỉ khác `id`; đây là một thành phần của danh tính, nên `equals` sai. Ba khóa `a,b,c` bằng nhau và `different` khác, vì vậy `HashSet` có **hai phần tử**.
5. Cặp `TextTag` cho thấy `Objects.equals` xử lý an toàn trường tham chiếu có thể `null`.
6. Cặp `Measurement` chứng minh `NaN` bằng nhau và hai số không `+0.0`/`-0.0` không bằng nhau theo `Double.compare`.
7. `ByteSequence` sao chép mảng đầu vào và mảng trả về. Dù bên ngoài sửa `source` và `exposed`, dữ liệu nội bộ không bị thay đổi: hai chuỗi byte vẫn bằng nhau và có mã băm bằng nhau.
8. `Point` là **record**. Vì không tự định nghĩa `equals/hashCode`, Java tạo các phương thức so sánh theo thành phần `x`, `y`, nên hai giá trị `Point(1,2)` bằng nhau.

## 6. `instanceof` và nguy cơ phá tính đối xứng khi có kế thừa

`obj instanceof Parent other` trả `true` không chỉ với đối tượng `Parent` mà còn với các đối tượng thuộc **lớp con** của `Parent`. Điều này giúp đa hình, nhưng có thể gây lỗi nếu lớp con định nghĩa thêm trường để so bằng nhau.

Xét mô hình sai về mặt hợp đồng (mã sau chỉ minh họa cấu trúc, không phải chương trình đầy đủ):

```java
class Parent {
    final int id;

    Parent(int id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof Parent other && id == other.id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }
}

class Child extends Parent {
    final String tag;

    Child(int id, String tag) {
        super(id);
        this.tag = tag;
    }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof Child other
                && id == other.id
                && java.util.Objects.equals(tag, other.tag);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(id, tag);
    }
}
```

Với `Parent p = new Parent(3);` và `Child c = new Child(3, "x");`, ta có:

- `p.equals(c) == true`, vì `c` cũng là một `Parent` và `id` bằng nhau.
- `c.equals(p) == false`, vì `p` không phải `Child`.

**Tính đối xứng bị vi phạm.** Đây là lỗi thiết kế kế thừa, không phải lỗi của bản thân pattern matching.

Những cách tránh trong thiết kế phù hợp:

- **Ưu tiên `final class`** cho kiểu giá trị nếu không cần kế thừa, như `UserKey` trong chương trình chạy được.
- Nếu chỉ muốn so **đúng lớp runtime**, có thể dùng `getClass() == obj.getClass()` rồi mới ép kiểu. Cách này không xem lớp con là bằng nhau với lớp cha, nhưng phải nhất quán với thiết kế toàn bộ hệ phân cấp.
- Nếu yêu cầu đa hình và so bằng nhau qua kế thừa, cần một chiến lược rõ ràng được các lớp trong hệ phân cấp tuân theo. Đừng kết hợp ngẫu nhiên `instanceof` ở lớp cha với điều kiện chặt hơn ở lớp con.
- **Record ngầm định `final`** và có `equals` theo cùng lớp record; khi dùng record chỉ để mang dữ liệu, thường không cần tự viết lại `equals`.

`getClass()` và `instanceof` không có đáp án đúng cho mọi hệ phân cấp; lựa chọn phải đi cùng **ý nghĩa danh tính** và hợp đồng đối xứng/bắc cầu.

## 7. So sánh trường: đủ, nhất quán và có chủ đích

Khi quyết định trường nào được dùng trong `equals`:

1. Ghi rõ **đối tượng biểu diễn điều gì**. Một `UserKey(tenant,id)` nên xét cả `tenant` và `id`; chỉ so `id` sẽ nhập nhằng khi hai tenant trùng ID.
2. Dùng phép so phù hợp với từng kiểu. `String` nên so bằng `equals` hoặc `Objects.equals`; mảng cần chọn so tham chiếu hay so nội dung theo yêu cầu thật sự.
3. Giữ **`hashCode` dùng cùng tập dữ liệu**. Không bỏ một trường trong `equals` nhưng lại thêm trường đó vào `hashCode` theo cách khiến hai đối tượng bằng nhau cho hai mã băm khác nhau.
4. Đảm bảo các trường tham gia so sánh không bị thay đổi bất ngờ nếu đối tượng được dùng trong bộ sưu tập băm.
5. Nếu cần chuẩn hóa chuỗi (bỏ khoảng trắng, chuyển chữ theo quy tắc nghiệp vụ), ưu tiên chuẩn hóa một lần trong constructor. Không so sánh kiểu “một bên chuẩn hóa, một bên không” dẫn đến mất tính đối xứng hoặc nhất quán.

### Ví dụ giá trị chuẩn hóa ngay khi xây dựng

```java
final class EmailKey {
    private final String normalized;

    EmailKey(String input) {
        normalized = java.util.Objects.requireNonNull(input)
                .strip()
                .toLowerCase(java.util.Locale.ROOT);
    }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof EmailKey other
                && normalized.equals(other.normalized);
    }

    @Override
    public int hashCode() {
        return normalized.hashCode();
    }
}
```

Đây là **một lớp Java độc lập** (đặt vào tệp `EmailKey.java`) minh họa cách giữ `equals/hashCode` ngắn. Lưu ý: đối với **địa chỉ email thật**, quy tắc phân biệt hoa thường/chuẩn hóa có thể phụ thuộc nghiệp vụ và hệ thống nhận thư; đừng tự áp dụng phép chuyển chữ ở trên nếu chưa xác định rằng đây chính xác là quy tắc danh tính cần dùng. Trong các miền khác, chuẩn hóa có thể có ý nghĩa khác.

## 8. Khi nào không cần tự viết `equals`?

Record đã chuẩn hóa từ Java 16 tạo sẵn `equals`, `hashCode` và `toString` theo các thành phần:

```java
record Point(int x, int y) {}

boolean equal = new Point(4, 5).equals(new Point(4, 5)); // true
```

Nếu yêu cầu là “hai record cùng lớp có **tất cả thành phần tương ứng bằng nhau**”, hãy giữ phương thức tự sinh. Dùng `instanceof` pattern tự viết trong `equals` của record chỉ khi thật sự cần ngữ nghĩa khác và phải bảo đảm hợp đồng với `hashCode` cũng như bất biến sao chép của record.

Tuy nhiên, cũng cần biết **bản `equals` mặc định của record không tự so sâu mảng**. Với `record Blob(byte[] data) {}`, hai mảng khác tham chiếu nhưng chứa byte giống nhau **không bằng nhau theo mặc định**; hãy thiết kế kiểu thành phần phù hợp hoặc tùy biến đồng bộ khi nghiệp vụ muốn so nội dung.

## 9. Những lỗi thường gặp và cách sửa

| Sai sót | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Viết `equals(UserKey)` thay vì `equals(Object)` | Chỉ overload, không thay `Object.equals` | Dùng đúng chữ ký và `@Override` |
| Dùng `(UserKey) obj` mà không kiểm tra kiểu | Có thể ném `ClassCastException` | Dùng `obj instanceof UserKey other` |
| Thêm `obj != null` dù đã dùng `instanceof` | Không sai nhưng thừa điều kiện | Nhớ `null instanceof T` là `false` |
| Thử dùng `other` sau một phép so khớp thất bại | Biến mẫu chưa được gán/ngoài phạm vi | Dùng `&&` hoặc nhánh `if` trả sớm |
| So `String` bằng `==` | So tham chiếu thay vì nội dung | Dùng `equals` / `Objects.equals` |
| So trường tham chiếu có thể `null` bằng `a.equals(b)` | Có thể ném `NullPointerException` | Dùng `Objects.equals(a, b)` |
| So mảng theo nội dung nhưng dùng `Objects.equals` | Vẫn so tham chiếu mảng | Dùng `Arrays.equals` và `Arrays.hashCode` |
| Ghi đè `equals` nhưng không điều chỉnh `hashCode` | Phá hợp đồng khóa của `HashMap`, `HashSet` | Ghi đè cả hai nhất quán |
| Dùng `instanceof` trên lớp cha có lớp con tùy biến phép so | Dễ phá tính đối xứng/bắc cầu | Cân nhắc `final`, kiểm tra đúng lớp, hoặc chiến lược đồng nhất |
| Dùng `==` cho `double` chứa `NaN` hoặc số không có dấu | Có thể khác quy tắc cần có và không tương thích hash | Dùng `Double.compare` + `Double.hashCode` |
| Để trường dùng trong `equals` thay đổi sau khi làm khóa băm | Tìm kiếm và loại trùng có thể sai | Dùng dữ liệu bất biến/defensive copy |
| Coi kiểm thử ba đối tượng là đã chứng minh hợp đồng mọi trường hợp | Các ca biên vẫn có thể sai | Bổ sung kiểm thử `null`, kiểu khác, giá trị biên, kế thừa và trạng thái mutable |

## 10. Tự luyện tập có đáp án

**Câu 1 — `null`:** Với `Object obj = null;`, biểu thức `obj instanceof UserKey other` là gì?  
**Đáp án:** `false`. Nó không ném `NullPointerException`, và `other` không có giá trị hợp lệ trên đường đi thất bại.

**Câu 2 — Ngắn gọn:** Viết kiểm tra kiểu trong `equals` không cần ép kiểu thủ công.  
**Đáp án:** `if (!(obj instanceof UserKey other)) return false;` hoặc `return obj instanceof UserKey other && ...;`, với `...` là các phép so trường.

**Câu 3 — So chuỗi:** Hai đối tượng `String` khác tham chiếu có cùng nội dung có thể bằng nhau không?  
**Đáp án:** Có, khi so bằng `String.equals`. `==` chỉ kiểm tra cùng tham chiếu.

**Câu 4 — Đối xứng:** Nếu `Parent.equals(Child)` trả `true` nhưng `Child.equals(Parent)` trả `false`, có đúng hợp đồng không?  
**Đáp án:** Không. Phép so bị mất tính đối xứng.

**Câu 5 — Mã băm:** Nếu `x.equals(y)` đúng thì có nhất thiết `x.hashCode() == y.hashCode()` không?  
**Đáp án:** Có. Chiều ngược lại không bắt buộc.

**Câu 6 — Số thực:** Tại sao cần cân nhắc `Double.compare`?  
**Đáp án:** Để định nghĩa rõ phép so với `NaN` và `+0.0/-0.0` và dùng `Double.hashCode` tương ứng.

**Câu 7 — Mảng:** Nếu một lớp chứa hai mảng byte khác tham chiếu nhưng cùng nội dung, viết `Arrays.equals` trong `equals` có đủ chưa?  
**Đáp án:** Chưa; nếu muốn làm kiểu giá trị ổn định, cần dùng `Arrays.hashCode` phù hợp và kiểm soát khả năng bên ngoài sửa mảng.

**Câu 8 — Record:** Có phải `record Point(int x, int y) {}` phải tự viết `equals` bằng `instanceof`?  
**Đáp án:** Không. Java tự tạo phép so theo thành phần; chỉ tùy biến nếu thực sự có yêu cầu khác và vẫn giữ hợp đồng.

## 11. Ghi nhớ và tài liệu chính thức

Một triển khai `equals` tốt cần **kiểm tra kiểu an toàn**, **so sánh đúng dữ liệu đại diện cho giá trị**, **giữ hợp đồng quan hệ tương đương** và **đồng bộ với `hashCode`**. Pattern matching cho `instanceof` giúp loại bỏ ép kiểu dư thừa và tạo phạm vi biến rõ ràng, nhưng không thay thế thiết kế danh tính.

- Với **`final class`**, mẫu `if (!(obj instanceof MyType other)) return false;` thường rất rõ ràng.
- Với **lớp có kế thừa**, phải giải quyết tính đối xứng và bắc cầu; đừng mặc nhiên rằng `instanceof` là đủ.
- Với **record**, ưu tiên bản `equals` tự sinh khi tất cả thành phần xác định danh tính.
- Với **mảng, số thực và tham chiếu có thể `null`**, chọn đúng phép so và mã băm tương ứng.
- Chỉ đưa những dữ liệu có khả năng duy trì nhất quán vào khóa `HashMap`/`HashSet`.

Tài liệu tham khảo hiện hành:

- [Java SE 17 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): cú pháp, phạm vi biến mẫu và toán tử ngắn mạch.
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): tính năng đã được chuẩn hóa ở Java 16.
- [Java SE 21 — `java.lang.Object.equals` và `hashCode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html): hợp đồng chuẩn của quan hệ bằng nhau và mã băm.
- [Java SE 21 — `Objects.equals` và `Objects.hash`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html): tiện ích so sánh `null` an toàn và tạo mã băm.
- [Oracle Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): `equals/hashCode` được tạo sẵn theo thành phần record.