# Trường `null` và `Objects.hashCode()` trong Java

## 1. Vấn đề khi trường tham gia `hashCode()` có thể bằng `null`

Một đối tượng có thể chứa trường tham chiếu chưa được gán giá trị, chẳng hạn `customerId` hoặc `region`. Nếu trường này là một phần bản sắc logic của đối tượng, `equals()` và `hashCode()` phải xử lý nó **nhất quán**, kể cả khi giá trị là `null`.

Gọi trực tiếp phương thức trên tham chiếu rỗng:

```java
String region = null;
int hash = region.hashCode(); // NullPointerException
```

Phần code trên là **fragment minh họa lỗi**, không phải chương trình chạy an toàn. Lỗi xảy ra vì `region` không trỏ đến đối tượng để gọi phương thức. Ta có thể dùng điều kiện `region == null ? 0 : region.hashCode()`, nhưng Java đã cung cấp một công cụ chuyên cho thao tác này: **`java.util.Objects.hashCode(Object)`**.

## 2. `Objects.hashCode(Object)` hoạt động thế nào?

Phương thức tĩnh:

```java
int hash = java.util.Objects.hashCode(value);
```

trả về:

- **`0`** nếu `value == null`;
- **`value.hashCode()`** nếu `value != null`.

Có thể hiểu quy tắc bằng biểu thức tương đương:

```java
static int nullSafeHash(Object value) {
    return value == null ? 0 : value.hashCode();
}
```

Đây là một đoạn khai báo phương thức minh họa; chỉ chứa một phương thức, chưa phải tệp Java hoàn chỉnh có `main`. `Objects.hashCode(value)` bảo vệ **lời gọi hash khi giá trị null**. Nó không tự tính “mã băm tối ưu”, không kiểm tra hay sửa hợp đồng của lớp cung cấp `value`.

Ví dụ:

| Giá trị `value` | `Objects.hashCode(value)` |
| --- | --- |
| `null` | `0` |
| `"A1"` | `2064`, bằng `"A1".hashCode()` |
| `Integer.valueOf(7)` | `7`, bằng `Integer.hashCode()` |
| Một đối tượng khác `null` | Kết quả của chính `value.hashCode()` |

Với chuỗi `"A1"`, `String.hashCode()` theo công thức đa thức: `31 * 'A' + '1' = 31 * 65 + 49 = 2064`.

**Đừng diễn giải `0` thành “chắc chắn null”.** Một đối tượng khác null vẫn được phép có mã băm `0`; các đối tượng không bằng nhau cũng có thể có cùng hash. Hash chỉ là giá trị phục vụ phân vùng/tìm kiếm, không phải bằng chứng tuyệt đối về tính bằng nhau.

## 3. Ví dụ Java 17+ chạy được

Trong ví dụ sau, `CustomerKey` đại diện cho khóa logic gồm hai trường `tenant` và `externalId`; cả hai có thể null. Ta dùng `Objects.equals()` khi so sánh và `Objects.hashCode()` khi tính mã băm từng trường. Hai phương thức tuân theo cùng tập trường nên tránh được việc `equals()` cho là bằng nhau nhưng `hashCode()` tính theo dữ liệu khác.

Tạo tệp `NullHashCodeDemo.java` chứa toàn bộ nội dung:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class NullHashCodeDemo {

    static final class CustomerKey {
        private final String tenant;
        private final String externalId;

        CustomerKey(String tenant, String externalId) {
            this.tenant = tenant;
            this.externalId = externalId;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof CustomerKey that)) {
                return false;
            }
            return Objects.equals(tenant, that.tenant)
                    && Objects.equals(externalId, that.externalId);
        }

        @Override
        public int hashCode() {
            int result = 1;
            result = 31 * result + Objects.hashCode(tenant);
            result = 31 * result + Objects.hashCode(externalId);
            return result;
        }
    }

    public static void main(String[] args) {
        System.out.println("Objects.hashCode(null): "
                + Objects.hashCode(null));
        System.out.println("Objects.hashCode(A1): "
                + Objects.hashCode("A1"));
        System.out.println("Objects.hash((Object) null): "
                + Objects.hash((Object) null));
        System.out.println("Objects.hash(A1): "
                + Objects.hash("A1"));

        CustomerKey a = new CustomerKey(null, "A1");
        CustomerKey b = new CustomerKey(null, "A1");
        CustomerKey c = new CustomerKey(null, "B2");
        CustomerKey d = new CustomerKey(null, null);

        System.out.println("a equals b: " + a.equals(b));
        System.out.println("a hash: " + a.hashCode());
        System.out.println("b hash: " + b.hashCode());
        System.out.println("a equals c: " + a.equals(c));
        System.out.println("d hash: " + d.hashCode());
        System.out.println("Objects.hash(null, A1): "
                + Objects.hash(null, "A1"));

        Set<CustomerKey> keys = new HashSet<>();
        keys.add(a);
        System.out.println("set contains b: " + keys.contains(b));
        System.out.println("set contains c: " + keys.contains(c));
    }
}
```

Chạy từ thư mục lưu tệp:

```bash
javac NullHashCodeDemo.java
java NullHashCodeDemo
```

Stdout dự kiến chính xác:

```text
Objects.hashCode(null): 0
Objects.hashCode(A1): 2064
Objects.hash((Object) null): 31
Objects.hash(A1): 2095
a equals b: true
a hash: 3025
b hash: 3025
a equals c: false
d hash: 961
Objects.hash(null, A1): 3025
set contains b: true
set contains c: false
```

Giải thích phép tính:

- Với `a`, ta khởi tạo `result = 1`; trường `tenant = null` cho `31 * 1 + 0 = 31`. Tiếp theo `externalId = "A1"` có hash `2064` nên kết quả là `31 * 31 + 2064 = 3025`.
- Với `d`, cả hai trường null: `31 * (31 * 1 + 0) + 0 = 961`. Điều này **không mâu thuẫn** với việc `Objects.hashCode(null) = 0`: `d.hashCode()` là hash **của cả đối tượng**, được kết hợp từ nhiều thành phần, còn `Objects.hashCode(null)` chỉ hash **một giá trị null**.
- `a` và `b` là hai instance khác nhau nhưng cùng `tenant` và `externalId`, vì vậy `equals()` đúng và hai hash đều bằng `3025`.
- `a` và `c` không bằng nhau vì `"A1"` khác `"B2"`. Mã băm khác hay trùng trong trường hợp không bằng nhau đều hợp lệ.
- `HashSet.contains(b)` trả về `true` sau khi thêm `a` vì cặp bằng nhau về logic và cùng hash. `contains(c)` là `false` vì không có khóa tương đương `c` trong tập.

Ví dụ cố ý dùng các trường `final String` để bản sắc logic không thay đổi khi khóa đang ở trong collection. `String` bất biến, do đó `hashCode()` cũng ổn định cho vòng đời đối tượng.

## 4. Đặc biệt chú ý: `Objects.hashCode(value)` khác `Objects.hash(values...)`

Hai phương thức có tên gần giống nhau nhưng chức năng **khác nhau**:

| Phương thức | Cơ chế | Khi nào dùng |
| --- | --- | --- |
| `Objects.hashCode(Object value)` | Null → `0`; còn lại gọi `value.hashCode()` | Lấy hash an toàn cho **một** giá trị nullable |
| `Objects.hash(Object... values)` | Kết hợp các phần tử qua thuật toán tương đương `Arrays.hashCode(Object[])` | Lấy hash kết hợp của **nhiều** trường |

Ví dụ:

```java
Objects.hashCode(null);       // 0
Objects.hash((Object) null);  // 31
Objects.hashCode("A1");       // 2064
Objects.hash("A1");           // 2095
Objects.hash(null, "A1");     // 3025
```

Đoạn trên là **fragment các biểu thức và kết quả**, không phải một chương trình riêng.

Tại sao `Objects.hash("A1") = 2095`? Với mảng varargs một phần tử, thuật toán `Arrays.hashCode` bắt đầu `result = 1` và tính `31 * 1 + 2064 = 2095`. Tương tự, mảng varargs một phần tử null cho `31 * 1 + 0 = 31`.

Phép gọi `Objects.hash((Object) null)` cố ý ép kiểu thành `Object`: nó chỉ định rõ **một phần tử null được truyền vào mảng varargs**, tránh nhầm với việc truyền trực tiếp một tham số có kiểu mảng null. Khi làm việc với varargs, `Objects.hash((Object[]) null)` có nghĩa khác: truyền **mảng tham số null**, và `Arrays.hashCode` của mảng null trả `0`. Không dựa vào các cách gọi mơ hồ để định nghĩa hash.

Quan trọng: chỉ cần tuân thủ **bằng nhau thì hash bằng nhau**. Không có yêu cầu `hashCode()` phải dùng đúng công thức của `Objects.hash()`; cách kết hợp `31 * result + ...` ở ví dụ và `Objects.hash(tenant, externalId)` là tương đương ở đây vì cùng khởi tạo `result = 1` và lần lượt xử lý hai trường.

`Objects.hash(...)` gọn và thường dễ đọc với vài trường, nhưng tạo một mảng varargs (có thể gây cấp phát/tốn tài nguyên tùy tối ưu runtime). Trong đoạn code thực thi cực thường xuyên, phép kết hợp thủ công có thể hữu ích sau khi đo lường. Không nên “tối ưu” khi chưa xác định nhu cầu.

## 5. Quan hệ giữa `equals()` và `hashCode()` khi có null

Hợp đồng cốt lõi của `Object` quy định: nếu `x.equals(y)` trả `true` thì **`x.hashCode() == y.hashCode()` bắt buộc đúng**. Chiều ngược lại không đúng: hai hash trùng nhau không buộc hai đối tượng bằng nhau.

Với trường nullable, hãy duy trì **cùng quy tắc xử lý null và cùng tập trường**:

```java
// Hai đoạn sau thuộc cùng class minh họa có field 'code':
@Override
public boolean equals(Object obj) {
    return obj instanceof Item that
            && Objects.equals(code, that.code);
}

@Override
public int hashCode() {
    return Objects.hashCode(code);
}
```

Đây là **fragment minh họa đặt trong class tên `Item` có trường `code`**, không phải chương trình hoàn chỉnh. Nó đúng về tính nhất quán trường `code` khi lớp là `final` hoặc chính sách bình đẳng theo lớp đã được thiết kế phù hợp. Trong thực tế vẫn cần xem xét lớp cha/lớp con, các thuộc tính khác và tính bất biến.

`Objects.equals(a, b)` hoạt động như sau: nếu hai tham chiếu cùng bằng null thì `true`; nếu chỉ một bên null thì `false`; nếu cả hai có giá trị thì gọi `a.equals(b)`. `Objects.hashCode(a)` không phải “phiên bản hash của hai đối số”, mà chỉ lấy hash một tham chiếu theo quy tắc null-safe.

Một cách cài đặt trực tiếp cũng hợp lệ:

```java
int codeHash = code == null ? 0 : code.hashCode();
```

Tuy nhiên `Objects.hashCode(code)` ngắn và dễ đọc hơn, đặc biệt khi có nhiều trường nullable. Đừng viết `code.hashCode()` trước khi kiểm tra null.

### Điều gì xảy ra nếu một trường không tham gia `equals()`?

Nếu `equals()` chỉ dựa trên `id` nhưng `hashCode()` tính thêm `description`, hai đối tượng có cùng `id` nhưng `description` khác nhau có thể có hash khác nhau, **vi phạm hợp đồng**. Ngược lại, hash bỏ bớt một số trường tham gia `equals()` có thể vẫn đúng về hợp đồng, nhưng gây nhiều va chạm. Tốt nhất nên tính hash trên các trường nhận diện giống `equals()`, trừ khi có lý do thiết kế được chứng minh.

Cả `equals()` và `hashCode()` đều phải ổn định khi những thông tin liên quan không thay đổi. Với đối tượng làm khóa trong `HashMap` hoặc phần tử của `HashSet`, tránh sửa các trường liên quan đến hash sau khi thêm vào collection; nếu giá trị thay đổi, tìm kiếm và xóa phần tử có thể thất bại.

## 6. Các bẫy cần tránh

### Bẫy A — nhầm `Objects.hashCode(null)` với hash toàn bộ đối tượng

`Objects.hashCode(null)` cho `0` nhưng object có hai trường null không nhất thiết cho hash `0`. Công thức kết hợp có seed, hệ số nhân hoặc dữ liệu kiểu khác có thể cho `961`, `31` hoặc giá trị khác. **Chỉ tính nhất quán với `equals()` mới là ràng buộc bắt buộc**, không có con số cố định dành cho đối tượng “có các trường null”.

### Bẫy B — gọi `Objects.hashCode(this)` bên trong chính `hashCode()`

Ví dụ sai:

```java
@Override
public int hashCode() {
    return Objects.hashCode(this); // Sai: đệ quy vô hạn
}
```

Vì `this` không null, `Objects.hashCode(this)` gọi lại `this.hashCode()` liên tục cho đến khi gây `StackOverflowError`. Hãy hash **các trường xác định bản sắc**, không gọi hash của chính đối tượng từ trong hàm đó.

### Bẫy C — mảng không được hash theo nội dung nếu chỉ dùng `Objects.hashCode(array)`

Một mảng Java thông thường kế thừa `Object.equals()/hashCode()`, nên hai mảng khác tham chiếu dù cùng phần tử vẫn không được xem là bằng nhau và có thể có hash khác nhau. Nếu định nghĩa bằng nhau **theo nội dung mảng**, chọn cặp thuật toán phù hợp:

- Mảng một chiều: `Arrays.equals(a, b)` và `Arrays.hashCode(a)` (có overload cho mảng nguyên thủy và object).
- Mảng nhiều tầng chứa mảng: khi cần so sánh nội dung lồng nhau, dùng `Arrays.deepEquals(a, b)` và `Arrays.deepHashCode(a)` cho các mảng `Object[]` thích hợp.

Nếu `equals()` so sánh nội dung mảng bằng `Arrays.equals` còn `hashCode()` dùng `Objects.hashCode(array)` thì hai đối tượng có mảng khác tham chiếu nhưng cùng nội dung có thể bằng nhau mà hash không bằng nhau. Đây là lỗi hợp đồng.

### Bẫy D — dùng hash làm kết quả so sánh bằng nhau

Không viết `return this.hashCode() == other.hashCode();` để cài đặt `equals()`. Hai đối tượng khác nhau có thể va chạm hash, nên phương thức như vậy có nguy cơ coi nhầm chúng bằng nhau. Cần so sánh dữ liệu nghiệp vụ xác định bản sắc.

### Bẫy E — tin rằng `Objects.hashCode` sửa được một lớp có `hashCode()` sai

`Objects.hashCode(nonNullValue)` chỉ ủy quyền sang `nonNullValue.hashCode()`. Nếu lớp đó vi phạm hợp đồng với `equals()` hoặc tạo kết quả không ổn định, `Objects.hashCode` không thể tự khắc phục. Chức năng đảm bảo duy nhất ở đây là **không gọi phương thức trên null**.

## 7. Khi nào không cần viết `hashCode()` thủ công?

Với một value object có vài trường phù hợp để so sánh theo giá trị, Java `record` có thể tự sinh `equals()` và `hashCode()`:

```java
record CustomerKeyRecord(String tenant, String externalId) {}
```

Đây là **đoạn khai báo type minh họa**, có thể đặt trong một tệp Java phù hợp. Hai record cùng kiểu và cùng cặp giá trị thành phần được xem bằng nhau, kể cả khi một hoặc hai thành phần null. Cách này giảm khả năng một phương thức dùng thiếu trường so với phương thức còn lại.

Tuy vậy, record **không tự biến dữ liệu mutable thành immutable sâu**. Nếu thành phần là mảng hoặc đối tượng có trạng thái thay đổi, cần xem xét chính sách sao chép, so sánh và hash. Record cũng không thay thế việc quyết định trường nào tạo nên bản sắc của bài toán.

## 8. Checklist kiểm tra nhanh

1. **Xác định trường nào tham gia bản sắc:** `equals()` so sánh những trường nào và `hashCode()` có sử dụng cùng thông tin tương ứng không?
2. **Kiểm tra null cả hai phía:** hai đối tượng cùng null ở một trường vẫn nên được xử lý an toàn và theo đúng quy tắc bằng nhau của trường đó; một bên null, một bên khác null cần phân biệt.
3. **Dùng đúng API:** `Objects.hashCode(field)` để hash một field nullable; `Objects.hash(field1, field2, ...)` để kết hợp nhiều trường. Không mặc định hai phương thức cho cùng kết quả nếu chỉ có một đối số.
4. **Xác nhận hợp đồng:** với mọi cặp `x, y` có `x.equals(y)` đúng, cần `x.hashCode() == y.hashCode()`. Hash giống nhau ở cặp không bằng nhau được phép.
5. **Tránh trạng thái thay đổi khi làm khóa:** ưu tiên đối tượng bất biến; nếu có trường mảng/nested object, kiểm tra định nghĩa so sánh và khả năng thay đổi nội dung.
6. **Thử trong collection:** thêm một key vào `HashSet`, tìm bằng một instance khác cùng dữ liệu và thử cả trường null/không null. Đây là bài kiểm chứng bổ sung, không thay thế việc kiểm tra hợp đồng.

Một kiểm thử nhỏ về cặp tương đương có thể viết như sau (fragment đặt trong test khi đã có `x` và `y`):

```java
if (x.equals(y) && x.hashCode() != y.hashCode()) {
    throw new AssertionError("equals/hashCode contract violated");
}
```

Thử thêm bộ dữ liệu null và không null. Một số test hữu hạn không đủ chứng minh mọi trường hợp; cần xem lại logic chọn trường và tính ổn định.

## 9. Tóm tắt kiến thức

- `Objects.hashCode(value)` trả `0` nếu `value` null, còn lại trả `value.hashCode()`. Nó giúp viết `hashCode()` không gặp `NullPointerException` với trường nullable.
- `Objects.hash(values...)` kết hợp nhiều giá trị theo thuật toán của `Arrays.hashCode(Object[])`; kể cả khi chỉ truyền một giá trị, kết quả **thường không trùng** `Objects.hashCode(value)`.
- Khi override `hashCode()`, dùng **cùng bản sắc logic** với `equals()`, luôn bảo đảm `x.equals(y) => x.hashCode() == y.hashCode()` và hạn chế dùng dữ liệu có thể thay đổi làm khóa.
- `null` cho mã băm `0` ở cấp **một giá trị** không có nghĩa cả đối tượng chứa nhiều trường null phải hash ra `0`. Các va chạm mã băm là hợp lệ và khác với quan hệ bằng nhau.
