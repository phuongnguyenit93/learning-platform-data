# `Objects` trong Java: Tạo mã băm nhiều trường và phân biệt `hash` với `hashCode`

## 1. Mục tiêu

`java.util.Objects` là lớp tiện ích có từ **Java 7**, vẫn được dùng trong Java 17+ và các phiên bản Java hiện hành. Hai phương thức dễ bị nhầm là:

- **`Objects.hashCode(Object o)`**: tính mã băm của **một đối tượng**, có xử lý `null`; trả `0` nếu đối số là `null`, nếu không trả `o.hashCode()`.
- **`Objects.hash(Object... values)`**: tính mã băm của **một dãy giá trị**; tiện khi triển khai `hashCode()` cho đối tượng có nhiều trường. Java tính như thể gom các đối số vào một mảng `Object[]` rồi gọi `Arrays.hashCode(Object[])`.

Còn **`Object.hashCode()`** là phương thức instance có trên mỗi object Java. Nó khác cả hai utility static nói trên: chính lớp đối tượng có thể **override `hashCode()`** để mã băm phản ánh ý nghĩa của `equals()`.

**Quy tắc sử dụng nhanh:**

```java
Objects.hashCode(value);           // một giá trị, null-safe
Objects.hash(first, second, third); // kết hợp nhiều giá trị
someObject.hashCode();             // gọi phương thức instance; NPE nếu reference null
```

Đoạn trên là minh họa lời gọi, giả định các biến đã được khai báo. Bài học không chỉ trình bày cú pháp mà còn làm rõ **mã băm nhiều trường, hợp đồng `equals`/`hashCode`, hiệu năng và trường hợp mảng**. Đây là các kiến thức còn áp dụng trong Java hiện đại; không cần phương thức hay thư viện đã lỗi thời.

## 2. Phân biệt ba tên rất giống nhau

| Cách gọi | Khai báo ở đâu? | Đầu vào | Khi đối tượng `null`? | Đích sử dụng |
| --- | --- | --- | --- | --- |
| `obj.hashCode()` | `java.lang.Object`, thường được override | `this`, không có tham số | Gọi trên tham chiếu `null` ném `NullPointerException` | Hợp đồng mã băm của đối tượng |
| `Objects.hashCode(obj)` | `java.util.Objects` | Một tham chiếu `Object` | Trả `0` | Lấy mã băm của một giá trị theo cách null-safe |
| `Objects.hash(a, b, c)` | `java.util.Objects` | `Object...`: một **dãy phần tử** | Mỗi phần tử `null` đóng góp `0`; cần phân biệt với cả mảng varargs `null` | Tổ hợp mã băm của nhiều trường |

Một số điểm dễ bỏ qua:

1. `Objects.hashCode(x)` không tạo một thuật toán băm mới cho `x`: với `x != null`, nó **gọi đúng `x.hashCode()`**.
2. `Objects.hash(x)` **không nói chung bằng** `Objects.hashCode(x)` dù chỉ truyền đúng một giá trị. Điều này được ghi rõ trong JDK API.
3. `Objects.hash(...)` là phương thức static của tiện ích `Objects`; **không có phương thức `Object.hash(...)` tương đương**.
4. `hashCode()` trả về kiểu `int`. Giá trị băm **có thể âm, bằng 0 hoặc trùng nhau** cho những đối tượng khác nhau; nó không phải ID, khóa mã hóa hay bằng chứng duy nhất về sự bằng nhau.

### 2.1. Ví dụ số đơn giản

```java
System.out.println(Objects.hashCode(7)); // 7
System.out.println(Objects.hash(7));     // 38
System.out.println(Objects.hash(1, 2));  // 994
```

Các lệnh minh họa ở trong phương thức có import `java.util.Objects`. Vì `7` được autobox thành `Integer` khi truyền cho utility nhận `Object`, `Objects.hashCode(7)` sử dụng `Integer.hashCode()` và thu được `7`.

Ngược lại, `Objects.hash(7)` xem đối số là **dãy chứa một phần tử**. Công thức kết hợp của `Arrays.hashCode(Object[])` bắt đầu từ `1`, nên:

- Một phần tử `7`: `31 × 1 + 7 = 38`.
- Hai phần tử `1, 2`: sau phần tử đầu là `31 × 1 + 1 = 32`, sau phần tử hai là `31 × 32 + 2 = 994`.

Đừng dùng `Objects.hash(field)` khi mục đích chỉ là lấy **mã băm vốn có** của chính `field`. Với một trường thông thường, `Objects.hashCode(field)` thường diễn đạt ý định rõ hơn và tránh chi phí tạo mảng varargs.

## 3. Cơ chế kết hợp mã băm nhiều giá trị

Theo đặc tả API, `Objects.hash(values)` tạo kết quả tương đương `Arrays.hashCode(Object[])` của dãy đối số. Với dãy không null:

```java
int result = 1;
for (Object value : values) {
    result = 31 * result + Objects.hashCode(value);
}
```

Đây là **mã giả minh họa nội bộ**, với `values` là `Object[]` đã có trong phạm vi. Đừng nhầm đoạn này với một API phải tự viết lại để dùng `Objects.hash(...)`.

Ý nghĩa:

- Khởi tạo giá trị tổng hợp từ `1`.
- Đi theo **thứ tự** các trường.
- Mỗi trường đóng góp mã băm riêng; `null` đóng góp `0`.
- Nhân `31` rồi cộng khiến vị trí/trình tự phần tử ảnh hưởng kết quả.
- Phép toán dùng `int` của Java, có thể tràn số 32-bit; đây là điều bình thường trong mã băm, không cần coi đó là lỗi nghiệp vụ.

Vì thứ tự có ảnh hưởng:

```java
int forward = Objects.hash("A", "B");
int reversed = Objects.hash("B", "A");
```

Hai giá trị **có thể khác nhau**; đừng đánh tráo thứ tự trường khi thay đổi một triển khai `hashCode()` mà không xem lại chính sách tính bằng nhau.

### 3.1. Các trường `null` và dãy rỗng

`Objects.hashCode(null)` chắc chắn trả `0`. `Objects.hash(...)` cần hiểu **hai mức khác nhau**: phần tử của dãy và chính mảng chứa dãy.

```java
Objects.hashCode(null);       // 0: một đối tượng null
Objects.hash((Object) null);  // 31: dãy chứa một phần tử null
Objects.hash((Object[]) null);// 0: chính mảng varargs là null
Objects.hash();               // 1: dãy không có phần tử
```

Đây là các kết quả kiểm tra được trên JDK 17. Cụ thể:

- `Objects.hash((Object) null)` tạo dãy **một phần tử** có giá trị `null`, nên kết quả là `31 * 1 + 0 = 31`.
- `Objects.hash((Object[]) null)` truyền **một tham chiếu mảng null** vào tham số varargs, tương đương `Arrays.hashCode((Object[]) null)`, trả `0`.
- `Objects.hash()` nhận một dãy rỗng, nên giá trị khởi tạo `1` không thay đổi.

**Tránh viết mơ hồ `Objects.hash(null)`** khi muốn kiểm tra một giá trị null: do cách Java xử lý varargs và overload/kiểu của literal `null`, trình biên dịch có thể coi đó là **mảng varargs null** và cảnh báo. Nếu thực sự muốn một **phần tử null**, viết rõ `Objects.hash((Object) null)`; nếu muốn băm một giá trị đơn lẻ, dùng `Objects.hashCode(null)`.

## 4. Băm nhiều trường cho một value object

### 4.1. Vấn đề của `equals` và `hashCode`

Giả sử một khóa khách hàng có các thuộc tính:

- `country`: quốc gia, có thể `null`.
- `id`: mã số nguyên.
- `tier`: phân hạng, có thể `null`.

Nếu hai đối tượng có cùng ba giá trị trên, ứng dụng coi chúng **bằng nhau về nội dung** dù được tạo từ hai lời gọi `new` khác nhau. Ta cần override cả `equals(Object)` và `hashCode()` theo **cùng tiêu chí**.

```java
static final class CustomerKey {
    private final String country;
    private final int id;
    private final String tier;

    CustomerKey(String country, int id, String tier) {
        this.country = country;
        this.id = id;
        this.tier = tier;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof CustomerKey that)) return false;

        return id == that.id
                && Objects.equals(country, that.country)
                && Objects.equals(tier, that.tier);
    }

    @Override
    public int hashCode() {
        return Objects.hash(country, id, tier);
    }
}
```

Đây là **lớp lồng minh họa**, có định nghĩa hoàn chỉnh trong chương trình chạy ở mục 8. Cú pháp `instanceof CustomerKey that` là pattern matching được hỗ trợ trên Java 17+, không phải cú pháp của Java 7. Riêng `java.util.Objects` và `Objects.hash`/`hashCode` đã có từ Java 7.

**Giải thích:**

1. `equals` dùng `id == that.id` vì `id` là primitive `int`.
2. `Objects.equals(a, b)` so sánh tham chiếu một cách null-safe, dựa vào `equals` của đối tượng không-null.
3. `hashCode` kết hợp **đúng ba trường dùng trong `equals`** bằng `Objects.hash(country, id, tier)`.
4. `int id` được autobox thành `Integer` để truyền qua `Object...`; mã băm của `Integer` bằng giá trị `int`.
5. Các trường `null` được xử lý; không cần viết biểu thức `tier == null ? 0 : tier.hashCode()` cho từng trường.

### 4.2. Vì sao phải đưa cùng tập trường vào cả hai?

Xét:

```java
CustomerKey a = new CustomerKey("VN", 17, null);
CustomerKey b = new CustomerKey("VN", 17, null);

System.out.println(a.equals(b));                 // true
System.out.println(a.hashCode() == b.hashCode()); // true
```

Nếu `equals` dựa trên `country`, `id`, `tier` nhưng `hashCode` lại băm một trường **không thuộc tiêu chí bằng nhau** (ví dụ ID phát sinh khác nhau cho mỗi object), hai object cùng nội dung có thể trả mã băm khác nhau và **vi phạm hợp đồng**.

Ngược lại, nếu `equals` dùng cả ba trường nhưng `hashCode` chỉ dùng `id`, điều đó **không nhất thiết vi phạm** yêu cầu equal ⇒ same hash, nhưng làm nhiều đối tượng khác nhau trùng băm hơn, có thể ảnh hưởng hiệu năng. Cách thường dễ bảo trì nhất là tính mã băm từ đúng những trường quyết định `equals`.

**Không có quy tắc “hash khác nhau thì equals chắc chắn false”?** Thực tế, nếu hai object tuân thủ hợp đồng mà mã băm khác nhau, chúng **không thể equal**. Nhưng chiều ngược lại **không đúng**: **hash bằng nhau không chứng minh equals true**.

## 5. Hợp đồng `equals`/`hashCode` và collection dựa trên băm

### 5.1. Ba điều kiện quan trọng của `hashCode`

Hợp đồng của `Object.hashCode()` yêu cầu:

1. **Ổn định trong một lần thực thi**, miễn thông tin được dùng để so sánh `equals` trên đối tượng không thay đổi.
2. **Hai đối tượng bằng nhau theo `equals` phải có cùng `hashCode`**.
3. Hai đối tượng **không bằng nhau vẫn được phép có cùng mã băm**; không cần duy nhất.

Các container như `HashMap` và `HashSet` thường dùng mã băm để tổ chức tra cứu, sau đó dùng `equals` để nhận diện khóa/phần tử tương ứng. Nếu chỉ override `equals` mà không override `hashCode` nhất quán, một tập hợp có thể lưu **hai đối tượng mà business logic coi là trùng nhau** hoặc không tìm được khóa như mong muốn.

```java
Set<CustomerKey> keys = new HashSet<>();
keys.add(new CustomerKey("VN", 17, null));
keys.add(new CustomerKey("VN", 17, null));

System.out.println(keys.size()); // 1
```

Đoạn trên là minh họa với `java.util.Set`, `java.util.HashSet` và lớp `CustomerKey` định nghĩa bên trên.

### 5.2. Va chạm băm (collision) là bình thường

`hashCode()` trả về đúng **32-bit `int`** trong khi số lượng đối tượng và trạng thái có thể lớn hơn nhiều. Việc hai giá trị khác nhau cùng hash là điều không tránh khỏi.

Ví dụ đáng nhớ:

```java
System.out.println("Aa".equals("BB")); // false
System.out.println("Aa".hashCode() == "BB".hashCode()); // true
```

Hai chuỗi không bằng nhau nhưng có cùng `String.hashCode()`. Điều này **không vi phạm** hợp đồng Java. Vì vậy:

- **Không** viết `return a.hashCode() == b.hashCode();` để triển khai `equals`.
- **Không** dùng mã băm làm khóa định danh duy nhất cho dữ liệu quan trọng.
- **Không** dùng `Objects.hash(...)` như mật mã, chữ ký số, MAC hoặc hàm băm mật khẩu. Nó không được thiết kế chống va chạm chủ động.
- **Không** suy ra rằng hai bản ghi có hash giống nhau là bản ghi giống nhau.

### 5.3. Khóa có thể thay đổi là một bẫy khác

Nếu một trường đóng góp vào `equals`/`hashCode` bị thay đổi **sau khi** đối tượng được thêm làm khóa trong `HashMap` hoặc phần tử trong `HashSet`, collection có thể lưu object ở vị trí được chọn theo hash cũ. Sau khi field đổi, tra cứu bằng hash mới có thể thất bại.

**Ưu tiên value object bất biến**: các trường khóa thường khai báo `final`; khi chứa collection hoặc mảng mutable, cần tạo bản sao phòng vệ hoặc dùng cấu trúc bất biến phù hợp. Viết `final int[] values` **chưa** khiến nội dung mảng bất biến, vì phần tử mảng vẫn sửa được.

## 6. Bẫy lớn: trường kiểu mảng và `Objects.hash(...)`

Mảng Java mặc định kế thừa `Object.equals`/`Object.hashCode` (so sánh và băm theo **identity**, không theo nội dung). Điều này gây lỗi khó thấy khi một object định nghĩa equality dựa trên **nội dung mảng**.

### 6.1. `Objects.hashCode(array)` không băm nội dung mảng

```java
int[] first = {2, 3};
int[] second = {2, 3};

System.out.println(Arrays.equals(first, second)); // true
System.out.println(
        Arrays.hashCode(first) == Arrays.hashCode(second)); // true
```

Ở đây `Arrays.equals(int[], int[])` và `Arrays.hashCode(int[])` cùng dựa trên nội dung. Nhưng:

```java
Objects.hashCode(first);  // gọi first.hashCode(), mặc định theo identity
Objects.hash(first);      // dãy một phần tử là int[]; băm phần tử theo identity
```

Hai biểu thức cuối **không băm nội dung các số 2, 3**. Vì vậy nếu `equals` của một lớp sử dụng `Arrays.equals(...)` cho trường mảng, `hashCode` cũng cần **`Arrays.hashCode(...)`** tương ứng; không nên đưa mảng thẳng vào `Objects.hash(...)` rồi cho rằng mọi phần tử bên trong được xét theo nội dung.

**Cách đúng cho trường `int[]`:**

```java
@Override
public int hashCode() {
    return 31 * Objects.hashCode(name)
            + Arrays.hashCode(components);
}
```

Trong cùng lớp, `equals` nên dùng `Objects.equals(name, other.name)` và `Arrays.equals(components, other.components)`. Phần ví dụ chạy bên dưới minh họa cặp triển khai này.

### 6.2. Mảng `Object[]` có thêm bẫy từ varargs

Chữ ký của `Objects.hash` là `Object... values`. Nếu đưa **trực tiếp một `Object[]`** vào, Java có thể dùng nó như **chính mảng varargs**, tức là từng phần tử của mảng trở thành từng giá trị được băm:

```java
Object[] items = {"x", 7};

Objects.hash(items);             // cùng kiểu tính với Arrays.hashCode(items)
Objects.hash((Object) items);    // một phần tử duy nhất: tham chiếu đến cả mảng
Objects.hashCode(items);         // gọi hashCode() của object mảng
Arrays.hashCode(items);          // băm nội dung ở mức một tầng
```

Hai lời gọi `Objects.hash(items)` và `Objects.hash((Object) items)` có **ngữ nghĩa khác nhau**, dù chỉ thêm một phép ép kiểu `(Object)`. Với `Objects.hash(items)`, đối số `Object[]` khớp với mảng chứa các phần tử varargs. Với `Objects.hash((Object) items)`, toàn bộ mảng được coi là **một phần tử** của dãy băm và mã băm của phần tử mảng mặc định là mã băm identity.

Với `int[]` không phải `Object[]`, lời gọi `Objects.hash(intArray)` thường coi cả mảng nguyên thủy là **một phần tử varargs duy nhất**, nên càng không thể hiểu nó tương đương `Arrays.hashCode(intArray)`.

**Nguyên tắc rõ ràng nhất:**

- Cần hash nội dung `int[]` hoặc một mảng primitive khác → `Arrays.hashCode(array)`.
- Cần hash nội dung `Object[]` ở mức một tầng → `Arrays.hashCode(array)`.
- Cần hash nội dung lồng nhau của `Object[]` → `Arrays.deepHashCode(array)`, khi phù hợp.
- Cần hash **các trường không phải mảng** của một object → `Objects.hash(field1, field2, ...)` thường tiện hơn.

### 6.3. Mảng lồng nhau: dùng cặp `deepEquals` / `deepHashCode`

Giả sử:

```java
Object[] a = {new int[]{2, 3}};
Object[] b = {new int[]{2, 3}};

System.out.println(Arrays.deepEquals(a, b)); // true
System.out.println(
        Arrays.deepHashCode(a) == Arrays.deepHashCode(b)); // true
```

`Arrays.hashCode(Object[])` chỉ băm một tầng: khi phần tử cũng là mảng, mặc định nó sử dụng mã băm của chính object mảng con. `Arrays.deepHashCode(Object[])` băm đệ quy theo nội dung mảng con (bao gồm mảng primitive), phù hợp với `Arrays.deepEquals(Object[], Object[])`.

**Cảnh báo hiện hành:** Không dùng `Arrays.deepHashCode` trên mảng `Object[]` **tự chứa nó trực tiếp hoặc gián tiếp**; đặc tả API quy định hành vi không xác định cho mảng lồng nhau có chu trình. Hãy thiết kế cấu trúc dữ liệu phù hợp thay vì mặc định deep hash xử lý được mọi đồ thị đối tượng.

### 6.4. Bảo vệ mảng trong value object

Với khóa lưu trong hash-based collection, không chỉ dùng `Arrays.hashCode` đúng mà còn phải **ngăn bên ngoài sửa nội dung mảng** sau khi tạo khóa.

```java
VectorKey(String name, int[] components) {
    this.name = name;
    this.components = components.clone(); // bản sao phòng vệ đầu vào
}
```

Nếu getter cần trả mảng, hãy cân nhắc `components.clone()` thay vì trả tham chiếu trực tiếp. Nếu mảng có thể chứa `null`, cần hợp đồng rõ cách xử lý trước khi gọi `clone()`; ví dụ này giả định input không-null.

## 7. Hiệu năng: tiện lợi của `Objects.hash` và khi nên viết thủ công

### 7.1. `Objects.hash(...)` rõ ràng, nhưng có chi phí

`Objects.hash(Object... values)` nhận một **mảng varargs**. Khi truyền nhiều trường tách rời, lời gọi có thể tạo mảng tạm và autobox các primitive như `int` hoặc `long` để đưa vào dãy `Object`. Trình biên dịch JIT có thể tối ưu một số allocation trong hoàn cảnh phù hợp, nhưng **không bảo đảm loại bỏ mọi allocation**.

Với những kiểu dữ liệu nhỏ, không chạy trên đường nóng (*hot path*) hàng triệu lần, ưu tiên code dễ đọc:

```java
@Override
public int hashCode() {
    return Objects.hash(country, id, tier);
}
```

Không nên tự tối ưu chỉ vì một giả định chung rằng `Objects.hash` luôn chậm đáng kể. Khi ứng dụng thực sự bị ảnh hưởng, hãy **đo bằng benchmark thích hợp** và tối ưu phần code có bằng chứng.

### 7.2. Khi cần tối ưu, tính theo công thức trực tiếp

Có thể tính mã băm tương đương cho ba trường không phải mảng:

```java
@Override
public int hashCode() {
    int result = 1;
    result = 31 * result + Objects.hashCode(country);
    result = 31 * result + Integer.hashCode(id);
    result = 31 * result + Objects.hashCode(tier);
    return result;
}
```

Ở đây:

- `Objects.hashCode(country)` và `Objects.hashCode(tier)` xử lý `null`.
- `Integer.hashCode(id)` xử lý primitive `int` mà không cần viết `new Integer(...)`.
- Trình tự cập nhật `result` giống cách kết hợp `Arrays.hashCode(Object[])` với ba phần tử tương ứng.
- Do Java dùng `int`, tràn số có thể xảy ra và vẫn phù hợp với công thức hash.

**Lưu ý:** Nếu thay thứ tự trường hoặc thay cách xử lý một trường (đặc biệt mảng, số thực, collection), kết quả có thể khác. Không mặc định mọi công thức hash “trông giống” đều tương đương từng bit. Điều bất biến bắt buộc vẫn là hợp đồng **equal ⇒ same hash**.

### 7.3. Đừng cache hash code nếu giá trị còn biến đổi

Có thể cache `hashCode` cho một value object **thực sự bất biến** và có yêu cầu hiệu năng đã đo, nhưng không nên cache vô điều kiện khi dữ liệu ảnh hưởng `equals` còn có thể bị sửa. Một cached hash cũ sẽ phá khả năng tra cứu của collection dựa trên băm.

Tương tự, đừng persist mã băm của object như một ID độc lập xuyên phiên bản/JVM. Hợp đồng `Object.hashCode` và triển khai cụ thể không hứa mọi loại object tạo lại trong lượt chạy khác sẽ có cùng mã băm. Nếu cần định danh ổn định, dùng ID nghiệp vụ riêng.

## 8. Chương trình Java 17+ đầy đủ và kết quả đã kiểm tra

Chương trình này minh họa:

- Sự khác nhau giữa `hash` và `hashCode` với **một đối số**.
- Suy luận đúng kết quả khi có nhiều số hoặc có `null`.
- Một `CustomerKey` dùng `Objects.hash` để đồng bộ với `equals`.
- Một `VectorKey` có trường mảng, dùng `Arrays.equals` và `Arrays.hashCode` để giữ tính nhất quán.
- Hiệu ứng `Object[]` khi truyền trực tiếp vào varargs.
- `deepHashCode` và trường hợp va chạm băm của hai chuỗi khác nhau.

Lưu nguyên tệp **`ObjectsHashVsHashCodeDemo.java`**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public final class ObjectsHashVsHashCodeDemo {

    static final class CustomerKey {
        private final String country;
        private final int id;
        private final String tier;

        CustomerKey(String country, int id, String tier) {
            this.country = country;
            this.id = id;
            this.tier = tier;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof CustomerKey that)) return false;

            return id == that.id
                    && Objects.equals(country, that.country)
                    && Objects.equals(tier, that.tier);
        }

        @Override
        public int hashCode() {
            return Objects.hash(country, id, tier);
        }
    }

    static final class VectorKey {
        private final String name;
        private final int[] components;

        VectorKey(String name, int[] components) {
            this.name = name;
            this.components = components.clone();
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof VectorKey that)) return false;

            return Objects.equals(name, that.name)
                    && Arrays.equals(components, that.components);
        }

        @Override
        public int hashCode() {
            return 31 * Objects.hashCode(name)
                    + Arrays.hashCode(components);
        }
    }

    public static void main(String[] args) {
        System.out.println("one.hashCode=" + Objects.hashCode(7));
        System.out.println("one.hash=" + Objects.hash(7));
        System.out.println("two.hash=" + Objects.hash(1, 2));
        System.out.println("null.hashCode=" + Objects.hashCode(null));
        System.out.println("null.asElement="
                + Objects.hash((Object) null));
        System.out.println("null.asArray="
                + Objects.hash((Object[]) null));
        System.out.println("zeroArguments=" + Objects.hash());

        CustomerKey a = new CustomerKey("VN", 17, null);
        CustomerKey b = new CustomerKey("VN", 17, null);

        System.out.println("keys.equal=" + a.equals(b));
        System.out.println("keys.hashEqual="
                + (a.hashCode() == b.hashCode()));

        Set<CustomerKey> keys = new HashSet<>();
        keys.add(a);
        keys.add(b);
        System.out.println("set.size=" + keys.size());

        VectorKey first = new VectorKey("point", new int[]{2, 3});
        VectorKey second = new VectorKey("point", new int[]{2, 3});

        System.out.println("vectors.equal=" + first.equals(second));
        System.out.println("vectors.hashEqual="
                + (first.hashCode() == second.hashCode()));

        int[] numbers = {2, 3};
        System.out.println("primitiveArray.hash="
                + Arrays.hashCode(numbers));

        Object[] items = {"x", 7};
        System.out.println("varargs.expand="
                + (Objects.hash(items) == Arrays.hashCode(items)));

        System.out.println("deep.hashEqual="
                + (Arrays.deepHashCode(new Object[]{new int[]{2, 3}})
                == Arrays.deepHashCode(new Object[]{new int[]{2, 3}})));

        System.out.println("collision="
                + ("Aa".hashCode() == "BB".hashCode()));
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac ObjectsHashVsHashCodeDemo.java
java ObjectsHashVsHashCodeDemo
```

**Stdout chính xác khi chạy với JDK 17:**

```text
one.hashCode=7
one.hash=38
two.hash=994
null.hashCode=0
null.asElement=31
null.asArray=0
zeroArguments=1
keys.equal=true
keys.hashEqual=true
set.size=1
vectors.equal=true
vectors.hashEqual=true
primitiveArray.hash=1026
varargs.expand=true
deep.hashEqual=true
collision=true
```

### 8.1. Giải thích từng nhóm kết quả

**Nhóm `hash` và `hashCode`:**

- `one.hashCode=7` và `one.hash=38` chứng minh **hai API không thể tráo đổi** ngay cả với một số nguyên.
- `two.hash=994` được tính bằng công thức dùng `31` và thứ tự hai phần tử.
- `null.hashCode=0` là hành vi null-safe của `Objects.hashCode`.
- `null.asElement=31` khác `null.asArray=0` vì một bên là **phần tử null**, bên kia là **mảng varargs null**.
- `zeroArguments=1` là mã băm của dãy rỗng theo `Arrays.hashCode(Object[])`.

**Nhóm value object:**

- `keys.equal=true` và `keys.hashEqual=true` xác nhận hai object khác tham chiếu nhưng cùng dữ liệu đáp ứng hợp đồng.
- `set.size=1` chứng minh `HashSet` nhận diện đúng hai khóa có cùng nội dung.
- `vectors.equal=true` và `vectors.hashEqual=true` chứng minh việc kết hợp `Arrays.equals`/`Arrays.hashCode` cho trường `int[]` giữ tính nhất quán.

**Nhóm mảng và va chạm:**

- `primitiveArray.hash=1026` là kết quả `Arrays.hashCode(new int[]{2, 3})`: `((1 × 31 + 2) × 31 + 3) = 1026`.
- `varargs.expand=true` xác nhận `Objects.hash(items)` với một `Object[]` trực tiếp có cùng kết quả như `Arrays.hashCode(items)`.
- `deep.hashEqual=true` so sánh mã băm theo **nội dung mảng con**.
- `collision=true` cho thấy hai chuỗi có nội dung khác nhau vẫn có thể có cùng mã băm; đây là điều được phép.

Tất cả lệnh trong chương trình đầy đủ đều sử dụng API có sẵn trong JDK; không cần dependency bên ngoài. Cú pháp `instanceof PatternVariable` cần Java 16+ (ở đây chọn Java 17), còn các utility `Objects.hash`/`hashCode` vẫn là kiến thức Java 7 có giá trị hiện tại.

## 9. Trường hợp Java `record` (Java 17+) có cần tự viết `hashCode` không?

Java hiện đại hỗ trợ record class cho dữ liệu mang tính value:

```java
record Customer(String country, int id, String tier) { }

Customer first = new Customer("VN", 17, null);
Customer second = new Customer("VN", 17, null);

System.out.println(first.equals(second)); // true
System.out.println(first.hashCode() == second.hashCode()); // true
```

Đoạn này là **minh họa đặt trong ngữ cảnh Java 17+**. Record tự sinh `equals` và `hashCode` từ các thành phần (`record components`), nên không cần override thủ công cho value object đơn giản.

**Hai lưu ý quan trọng:**

1. Thuật toán mã băm record tự sinh được JDK cho phép thay đổi chi tiết triển khai; **không giả định `record.hashCode()` bằng `Objects.hash(allComponents)`** hay có giá trị số cố định.
2. Với thành phần có kiểu mảng, `equals` mặc định của record dùng cách so sánh của reference, tức là **không tự động so sánh nội dung mảng**. Nếu nghiệp vụ yêu cầu so sánh sâu theo nội dung, cần thiết kế lại kiểu dữ liệu hoặc override `equals`/`hashCode` nhất quán; đồng thời xử lý tính mutable bằng bản sao phòng vệ.

Dùng record có thể giúp code ngắn hơn, nhưng nó không thay thế hiểu biết về hợp đồng hash/equals và đặc điểm của mảng.

## 10. Sai lầm phổ biến

| Sai lầm | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| Dùng `Objects.hash(x)` thay `Objects.hashCode(x)` vì “chỉ có một trường” | Kết quả thường khác, do `hash` băm một dãy | Khi muốn mã băm trực tiếp một giá trị, dùng `hashCode` |
| Dùng `Objects.hash(x, y)` làm mã định danh duy nhất | Có thể va chạm, chỉ trả `int` 32-bit | Dùng khóa nghiệp vụ ổn định |
| Override `equals` nhưng quên `hashCode` | Có thể phá tính đúng đắn của hash-based collections | Override cả hai theo cùng thông tin |
| Dùng `hashCode` trong `equals` thay so sánh trường | Collision làm hai object khác nhau bị coi là bằng | So sánh trường bằng `equals`/`Arrays.equals` thích hợp |
| Hash trên trường mutable đã đưa vào `HashMap` | Hash có thể đổi sau khi lưu | Value key bất biến, defensive copy khi cần |
| Gọi `Objects.hash(array)` để mong hash nội dung `int[]` | Mảng primitive được băm theo identity như phần tử của varargs | `Arrays.hashCode(int[])` |
| Gọi `Objects.hashCode(Object[])` để mong hash nội dung | Gọi `hashCode()` của chính object mảng | `Arrays.hashCode(Object[])` |
| Không nhận ra `Objects.hash(objectArray)` có thể mở rộng varargs | Thay đổi cách hiểu đối số; dễ khác ý định | Dùng `Arrays.hashCode(array)` nếu thật sự muốn hash nội dung |
| Dùng `Arrays.hashCode` cho mảng lồng nhau nhưng `deepEquals` khi so sánh | Một bên một tầng, bên kia so sánh sâu | Dùng cặp `deepEquals`/`deepHashCode` cho cấu trúc phù hợp |
| Cho rằng `Objects.hashCode(null)` gây NPE | Utility này được thiết kế null-safe | Dùng đúng API và phân biệt với `obj.hashCode()` |
| Cho rằng mọi đối tượng cùng giá trị logic đều có mã băm ổn định xuyên JVM | Chỉ được đảm bảo theo hợp đồng từng lớp/phiên chạy | Không persist hashCode như ID |
| Tự tối ưu mọi `Objects.hash` bằng phép nhân 31 | Có thể làm code khó đọc mà không cải thiện thực tế | Đo hiệu năng rồi mới tối ưu hot path |

## 11. Checklist khi triển khai `hashCode()` nhiều trường

- [ ] Đã xác định rõ những trường nào quyết định `equals`.
- [ ] Nếu hai object `equals` nhau thì toàn bộ thông tin đưa vào hash **tương thích**.
- [ ] Có thể dùng `Objects.hash(field1, field2, ...)` khi các trường đều có `hashCode` nhất quán.
- [ ] Khi băm một giá trị đơn lẻ, đã phân biệt `Objects.hashCode(value)` và `Objects.hash(value)`.
- [ ] Đã kiểm tra trường có thể `null`; không dereference không cần thiết.
- [ ] Với mảng primitive, dùng `Arrays.equals` và `Arrays.hashCode` tương ứng.
- [ ] Với mảng object lồng nhau, đã cân nhắc `deepEquals`/`deepHashCode` và nguy cơ chu trình.
- [ ] Nếu class chứa mảng mutable, đã bảo vệ đầu vào và đầu ra khỏi chỉnh sửa ngoài ý muốn.
- [ ] Không dùng mã băm thay cho ID duy nhất, kiểm tra nội dung hoặc bảo mật.
- [ ] Có test: equal ⇒ same hash; các object khác nhau với cùng key được `HashSet`/`HashMap` xử lý đúng.
- [ ] Không thay đổi hash-relevant fields khi object đang được dùng làm khóa trong collection.
- [ ] Nếu quan tâm hiệu năng, đã đo đạc tác động varargs/boxing trước khi viết công thức thủ công.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `Objects.hashCode(null)` và `Objects.hash((Object) null)` có cùng kết quả không?  
**Đáp án:** Không. Trường hợp đầu trả `0`, trường hợp thứ hai băm dãy một phần tử null nên trả `31`.

**Câu 2.** Tại sao `Objects.hash(1, 2)` cho `994`?  
**Đáp án:** Từ `result=1`, xử lý phần tử `1` thành `32`, sau đó phần tử `2` thành `31×32+2=994`.

**Câu 3.** Hai object có `hashCode()` bằng nhau thì `equals()` phải bằng `true`?  
**Đáp án:** Không. Collision được phép; yêu cầu bắt buộc chỉ theo chiều `equals ⇒ cùng hash`.

**Câu 4.** Nếu lớp có `String name` và `int[] values`, trong `equals` so sánh `Arrays.equals(values, other.values)`, có nên dùng `Objects.hash(name, values)` trong `hashCode` không?  
**Đáp án:** Không, vì mã băm của `int[]` ở vị trí phần tử varargs dùng identity theo mặc định. Cần kết hợp `Objects.hashCode(name)` với `Arrays.hashCode(values)`, chẳng hạn bằng công thức nhân 31.

**Câu 5.** `Objects.hash(items)` với `items` có kiểu `Object[]` có cùng ý nghĩa với `Objects.hash((Object)items)` không?  
**Đáp án:** Không. Không ép kiểu thì mảng có thể là toàn bộ dãy varargs; ép sang `Object` thì cả mảng là **một** phần tử.

**Câu 6.** Vì sao record Java 17+ thường không cần tự viết `hashCode()`?  
**Đáp án:** Compiler tự sinh `equals`/`hashCode` từ các record components. Tuy nhiên, mảng component vẫn có ngữ nghĩa tham chiếu mặc định và cần xử lý riêng nếu muốn so sánh nội dung.

**Câu 7.** Có nên lưu `Objects.hash(a,b,c)` vào database như ID ổn định và duy nhất?  
**Đáp án:** Không. Mã băm 32-bit có collision và không thay thế hợp đồng định danh của ứng dụng.

## 13. Kết luận và tài liệu chính thức

**Ghi nhớ cốt lõi:**

- **`Objects.hashCode(x)`**: lấy hash của **một giá trị** theo cách null-safe.
- **`Objects.hash(x, y, z)`**: kết hợp hash của **nhiều giá trị có thứ tự** theo mô hình `Arrays.hashCode(Object[])`.
- **`obj.hashCode()`**: phương thức của chính đối tượng; override cùng `equals` khi xây dựng value object.
- **Mảng cần xử lý riêng theo nội dung**: `Arrays.hashCode`/`Arrays.equals` hoặc `deepHashCode`/`deepEquals`; đừng tưởng `Objects.hash` tự đi sâu vào mọi mảng.
- **Băm không thay cho bằng nhau hay mã định danh**. Equal objects phải có cùng hash; đối tượng khác nhau vẫn có thể có cùng hash.

### Tài liệu Oracle còn hiệu lực

- [Java SE 17 — `java.util.Objects`, `hash(Object...)` và `hashCode(Object)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html).
- [Java SE 17 — `java.util.Arrays`, `hashCode`, `deepHashCode`, `equals` và `deepEquals`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html).
- [Java SE 17 — `java.lang.Object.hashCode()` và hợp đồng `equals`/`hashCode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()).
- [Java SE 17 — `java.lang.Record`, hợp đồng sinh `equals`/`hashCode` từ components](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).