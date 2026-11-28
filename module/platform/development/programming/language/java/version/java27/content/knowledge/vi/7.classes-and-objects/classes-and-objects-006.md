# Hợp đồng `equals`, `hashCode` và `toString` trong Java 27

Khi làm việc với lớp và đối tượng trong **Java 27**, ba phương thức kế thừa từ `java.lang.Object` quyết định những hành vi rất thực tế:

- `equals(Object)` cho biết hai đối tượng có được xem là **bằng nhau** theo quy tắc của kiểu dữ liệu hay không.
- `hashCode()` cung cấp giá trị băm phù hợp với quy tắc bằng nhau, giúp các cấu trúc như `HashMap` và `HashSet` hoạt động đúng.
- `toString()` trả về cách biểu diễn đối tượng bằng văn bản để người đọc hiểu trạng thái của nó.

Cả ba phương thức đều có thể được ghi đè (*override*). Tuy nhiên, chúng không phải ba thao tác độc lập: **thay đổi định nghĩa bằng nhau thường kéo theo việc phải thay đổi cách tính mã băm**. Chuỗi do `toString()` tạo ra dùng để quan sát, không mặc nhiên là khóa định danh hoặc định dạng lưu trữ dữ liệu.

Bài học này tập trung vào các hợp đồng vẫn áp dụng cho Java SE 27, cùng cách triển khai hiện đại cho lớp thường và `record`.

## 1. Phân biệt cùng một đối tượng và hai đối tượng có giá trị bằng nhau

Với hai biến tham chiếu tới đối tượng, toán tử `==` kiểm tra **đồng nhất tham chiếu** (*reference identity*): hai biến có tham chiếu tới cùng một đối tượng hay không. Trong khi đó, `equals` có thể diễn tả **bình đẳng theo giá trị** (*value equality*), tùy cách lớp triển khai.

```java
String a = new String("java");
String b = new String("java");

System.out.println(a == b);      // false: hai đối tượng String khác nhau
System.out.println(a.equals(b)); // true: cùng chuỗi ký tự
```

`String` đã ghi đè `equals` để so sánh nội dung. Ngược lại, `Object.equals` mặc định chỉ trả về `true` khi hai tham chiếu trỏ tới cùng một đối tượng, tương đương `==` đối với hai tham chiếu không `null`.

```java
Object first = new Object();
Object second = new Object();

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // false
System.out.println(first.equals(first));  // true
```

Không có quy tắc rằng *mọi lớp đều cần so sánh theo giá trị*. Ví dụ, một đối tượng biểu diễn phiên làm việc, kết nối hoặc thực thể có vòng đời và danh tính riêng có thể cần giữ semantics theo identity. Với một giá trị bất biến như mã địa chỉ, tọa độ hoặc khóa nghiệp vụ, so sánh theo giá trị thường phù hợp hơn.

| Phép so sánh | Với đối tượng Java | Câu hỏi trả lời |
| --- | --- | --- |
| `a == b` | So sánh tham chiếu (khi `a` và `b` có kiểu tham chiếu) | Có phải chính cùng một đối tượng? |
| `a.equals(b)` | Gọi phương thức của `a` | Có được coi là bằng nhau theo kiểu của `a`? |
| `Objects.equals(a, b)` | So sánh có xử lý `null` | Hai giá trị có bằng nhau, kể cả khi một hoặc cả hai là `null`? |

Với kiểu nguyên thủy như `int`, `==` so sánh giá trị; các kiểu nguyên thủy không có phương thức `equals`.

## 2. Hợp đồng `equals(Object)`

Phương thức cần ghi đè có chữ ký:

```java
@Override
public boolean equals(Object other) {
    // Trả về true hoặc false theo quy tắc bằng nhau của lớp.
}
```

Theo đặc tả `Object.equals` của Java 27, quan hệ bằng nhau trên các tham chiếu khác `null` phải tuân thủ năm quy tắc:

| Quy tắc | Biểu thức hoặc điều kiện | Ý nghĩa |
| --- | --- | --- |
| **Phản xạ (reflexive)** | `x.equals(x) == true` | Một đối tượng phải bằng chính nó. |
| **Đối xứng (symmetric)** | `x.equals(y) == y.equals(x)` | Đổi thứ tự so sánh không đổi kết quả. |
| **Bắc cầu (transitive)** | Nếu `x` bằng `y` và `y` bằng `z`, thì `x` bằng `z` | Không tạo các nhóm “bằng nhau” mâu thuẫn. |
| **Nhất quán (consistent)** | Lặp lại phép so sánh cho cùng kết quả nếu dữ liệu so sánh không đổi | Không tự ý thay kết quả do thời gian, số lần gọi hoặc trạng thái bên ngoài. |
| **Với `null`** | `x.equals(null) == false` khi `x != null` | Một đối tượng thật không bằng `null`. |

Ví dụ, nếu hai đối tượng `CustomerKey("VN", "C101")` và `CustomerKey("VN", "C101")` được coi là cùng một khóa, quan hệ bằng nhau phải đúng theo cả hai chiều và phải tiếp tục đúng khi các thành phần khóa không thay đổi.

### 2.1. Xác định trường nào tạo nên bình đẳng

Định nghĩa `equals` dựa trên **ngữ nghĩa nghiệp vụ**, không đơn thuần dựa trên “so sánh tất cả trường”.

Giả sử mã khách hàng có thể trùng giữa hai vùng dữ liệu. Khóa định danh cần cả `tenantId` và `customerId`:

```text
CustomerKey(tenantId = "north", customerId = "C101")
CustomerKey(tenantId = "south", customerId = "C101")
```

Hai giá trị trên **khác nhau**, dù `customerId` giống nhau. Ngược lại, các thuộc tính phụ như thời điểm cuối cùng tra cứu hoặc số lần truy cập không nên tham gia `equals` nếu chúng không thuộc danh tính logic.

Một câu hỏi thiết kế hữu ích: “Nếu hai đối tượng `equals` trả về `true`, ứng dụng có thể thay đối tượng này bằng đối tượng kia trong những tình huống nào?” Câu trả lời nên thống nhất với semantics của miền dữ liệu.

### 2.2. Ghi đè đúng chữ ký, tránh tạo một overload khác

Cách dưới đây **không ghi đè** `Object.equals`:

```java
// Sai nếu muốn override phương thức của Object.
public boolean equals(CustomerKey other) {
    // ...
}
```

Đây là một phương thức *overload*. Lời gọi thông qua tham chiếu có kiểu `Object` hoặc qua framework/collection vẫn có thể sử dụng `equals(Object)` mặc định.

Hãy dùng chính xác `public boolean equals(Object other)` và gắn `@Override`. Nếu sai chữ ký, compiler sẽ báo lỗi thay vì âm thầm tạo overload ngoài ý muốn.

## 3. Hợp đồng `hashCode()` và quan hệ với `equals`

Phương thức `hashCode()` có chữ ký:

```java
@Override
public int hashCode() {
    // Tính mã băm tương ứng với dữ liệu trong equals.
}
```

Theo đặc tả `Object.hashCode`, ba nguyên tắc quan trọng là:

1. Gọi nhiều lần trên cùng đối tượng trong một lần chạy phải trả về cùng số nguyên, **nếu thông tin dùng trong `equals` không thay đổi**.
2. **Nếu `a.equals(b)` đúng thì `a.hashCode() == b.hashCode()` bắt buộc đúng.**
3. Nếu `a.equals(b)` sai, hai mã băm **vẫn có thể giống nhau**. Đây gọi là *hash collision*; không phải vi phạm hợp đồng.

Có thể viết ngắn gọn điều kiện bắt buộc:

```text
a.equals(b) == true   =>   a.hashCode() == b.hashCode()

a.hashCode() == b.hashCode()   KHÔNG suy ra   a.equals(b) == true
```

Một mã băm là số nguyên `int` 32 bit, không phải khóa định danh duy nhất, số thứ tự, địa chỉ bộ nhớ, chữ ký mật mã hay giá trị bảo mật. Hợp đồng cũng **không yêu cầu** mã băm giữ nguyên giữa các lần chạy JVM khác nhau.

### 3.1. Vì sao `HashMap` và `HashSet` cần cả hai?

Về mặt khái niệm, khi thêm hoặc tra cứu một khóa, cấu trúc băm dùng `hashCode` để chọn vùng tìm kiếm ứng viên và dùng phép bằng nhau để xác nhận khóa phù hợp. Chi tiết thuật toán nội bộ phụ thuộc vào triển khai, nhưng hệ quả thiết kế là:

- Hai khóa bằng nhau mà trả về **mã băm khác nhau** có thể bị tra cứu ở những vị trí khác nhau, dẫn đến `get` hoặc `contains` không tìm thấy giá trị mong muốn.
- Hai khóa không bằng nhau nhưng có **cùng mã băm** vẫn hợp lệ. Collection phải giải quyết va chạm và tiếp tục phân biệt chúng bằng quan hệ bằng nhau.
- Chọn cách tính mã băm phân tán hợp lý giúp hiệu năng tốt hơn; nhưng hiệu năng không được đánh đổi bằng việc vi phạm quy tắc bằng nhau.

Vì vậy, với một lớp dùng value equality, hãy triển khai `equals` và `hashCode` **cùng lúc**, dựa trên cùng bộ trường dữ liệu. Việc chỉ ghi đè `equals` mà giữ `Object.hashCode` mặc định là lỗi phổ biến.

## 4. Hợp đồng `toString()`

`toString()` trả về cách biểu diễn đối tượng bằng một `String`:

```java
@Override
public String toString() {
    return "CustomerKey[tenantId=" + tenantId + ", customerId=" + customerId + "]";
}
```

Tài liệu Java 27 yêu cầu một triển khai đúng hợp đồng của `toString` trả về **giá trị không `null`**. Chuỗi nên súc tích, có đủ thông tin để người đọc nhận ra trạng thái quan trọng.

Mặc định `Object.toString()` tạo dạng tương tự:

```text
com.example.CustomerKey@7a46a697
```

Nó ghép tên lớp, dấu `@` và biểu diễn hex của mã băm theo `hashCode()`. Phần sau dấu `@` **không nhất thiết là địa chỉ bộ nhớ**. Nếu chỉ cần chuỗi thể hiện identity để chẩn đoán, Java hiện đại còn có `Objects.toIdentityString(object)`, không gọi các phương thức ghi đè của đối tượng.

Chuỗi do `toString` tạo ra không được bảo đảm có cùng định dạng qua các phiên bản của lớp hay các lần chạy JVM. Vì vậy:

- Dùng cho log, debug, hiển thị kỹ thuật khi thông tin đủ an toàn.
- Không dùng như khóa bền vững trong database, thông điệp API cần schema hoặc định dạng serialize chính thức.
- Không tiết lộ mật khẩu, token truy cập, khóa API, thông tin định danh nhạy cảm hoặc dữ liệu riêng tư chỉ vì đang muốn debug.
- Tránh tác dụng phụ, truy vấn mạng/DB, xử lý quá tốn kém và đệ quy vô hạn khi hai đối tượng trỏ vòng nhau.

**`toString` không tham gia trực tiếp hợp đồng của `equals` và `hashCode` đối với lớp thường.** Hai đối tượng bằng nhau có thể có chuỗi biểu diễn khác nhau nếu lớp thêm thông tin chẩn đoán vào `toString`. Tuy nhiên, đối với *record*, đặc tả có thêm yêu cầu riêng được trình bày ở phần sau.

## 5. Ví dụ hoàn chỉnh: lớp khóa giá trị bất biến

Xét lớp `CustomerKey` là khóa định danh khách hàng trong một tenant. Lớp được đánh dấu `final` để không có lớp con mở rộng semantics của phép bằng nhau; hai trường `String` đều `final` và được kiểm tra khác `null`.

Tạo file `EqualityDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class EqualityDemo {

    static final class CustomerKey {
        private final String tenantId;
        private final String customerId;

        CustomerKey(String tenantId, String customerId) {
            this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
            this.customerId = Objects.requireNonNull(customerId, "customerId");
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof CustomerKey that)) {
                return false;
            }
            return tenantId.equals(that.tenantId)
                    && customerId.equals(that.customerId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, customerId);
        }

        @Override
        public String toString() {
            return "CustomerKey[tenantId=" + tenantId
                    + ", customerId=" + customerId + "]";
        }
    }

    public static void main(String[] args) {
        var first = new CustomerKey("north", "C101");
        var second = new CustomerKey("north", "C101");
        var third = new CustomerKey("south", "C101");

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.equals(third));
        System.out.println(first.hashCode() == second.hashCode());

        Set<CustomerKey> uniqueKeys = new HashSet<>();
        uniqueKeys.add(first);
        uniqueKeys.add(second);
        uniqueKeys.add(third);
        System.out.println(uniqueKeys.size());

        Map<CustomerKey, String> descriptions = new HashMap<>();
        descriptions.put(first, "Khách hàng hợp lệ");
        System.out.println(descriptions.get(second));

        System.out.println(first);
    }
}
```

Biên dịch và chạy bằng JDK 27:

```bash
javac EqualityDemo.java
java EqualityDemo
```

Kết quả theo thứ tự:

```text
false
true
false
true
2
Khách hàng hợp lệ
CustomerKey[tenantId=north, customerId=C101]
```

**Vì sao hoạt động?**

- `first` và `second` được tạo bằng hai lần `new` nên `==` trả về `false`.
- Hai giá trị có cùng `tenantId` và `customerId` nên `equals` trả về `true`.
- `hashCode` kết hợp đúng hai trường tạo nên bình đẳng, nên hai khóa bằng nhau luôn có cùng mã băm.
- `HashSet` chỉ giữ một phần tử cho cặp giá trị `first`/`second`; `third` thuộc tenant khác nên được giữ riêng.
- `HashMap.get(second)` tìm thấy dữ liệu đã gắn với `first`.
- `toString` cung cấp chuỗi dễ đọc, thay cho biểu diễn mặc định khó hiểu.

Chọn `Objects.hash(tenantId, customerId)` thuận tiện cho ví dụ và mã ứng dụng thông thường. Với đoạn code cực kỳ nhạy cảm hiệu năng, có thể tính băm thủ công từ các trường và cân nhắc chi phí của lời gọi varargs, nhưng vẫn phải giữ đúng cùng các quy tắc hợp đồng.

## 6. `Objects.equals`, `Objects.hash` và `Objects.toString`

Lớp tiện ích `java.util.Objects` là API chuẩn hiện hành, giúp xử lý nhiều thao tác phổ biến:

| API | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `Objects.equals(a, b)` | So sánh an toàn khi một hoặc hai tham chiếu là `null` | Trả về `true` nếu cùng là `null`, nếu khác thì dùng `a.equals(b)`. |
| `Objects.hashCode(value)` | Lấy băm của một đối tượng có thể `null` | Với `null`, trả về 0. |
| `Objects.hash(a, b, ...)` | Kết hợp băm của một danh sách thành phần | Dùng cho các trường cấu thành value equality. |
| `Objects.toString(value)` | Lấy chuỗi của một đối tượng có thể `null` | Với `null`, trả về chuỗi `"null"`. |
| `Objects.toString(value, defaultText)` | Biểu diễn có giá trị mặc định | Dùng `defaultText` khi `value == null`. |
| `Objects.toIdentityString(value)` | Biểu diễn kiểu Object mặc định theo identity | Có từ Java 19; không gọi `toString` ghi đè. |

Ví dụ với một lớp cho phép trường `displayName` không có giá trị:

```java
@Override
public boolean equals(Object other) {
    return other instanceof Profile that
            && id.equals(that.id)
            && Objects.equals(displayName, that.displayName);
}

@Override
public int hashCode() {
    return Objects.hash(id, displayName);
}
```

*Đoạn trên là minh họa hai phương thức bên trong một lớp `Profile` có trường `id` và `displayName`; trong dự án thực tế, hãy xác định rõ liệu `displayName` có thuộc identity logic hay không trước khi đưa vào cả hai phương thức.*

Chú ý phân biệt `Objects.hashCode(x)` với `Objects.hash(x)`: chúng không có nghĩa vụ trả về cùng một mã băm. Đặc biệt, với **mảng**, `Objects.hash` sử dụng varargs và có thể gây nhầm lẫn; muốn so sánh phần tử mảng hãy sử dụng đúng tiện ích `Arrays`.

## 7. `record`: tự sinh ba phương thức theo các thành phần dữ liệu

Với một nhóm giá trị bất biến đơn giản, `record` là lựa chọn ngôn ngữ hiện đại, được hỗ trợ ổn định trong Java 27:

```java
record CustomerKey(String tenantId, String customerId) {
    CustomerKey {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(customerId, "customerId");
    }
}
```

Ví dụ cần `import java.util.Objects;` ở đầu tệp. Nếu không khai báo thủ công, compiler tự sinh `equals(Object)`, `hashCode()` và `toString()` từ các *record component*. Cụ thể:

- Hai record chỉ bằng nhau nếu thuộc **cùng record class** và các component tương ứng bằng nhau.
- Với component kiểu tham chiếu, bình đẳng theo quy tắc tương đương `Objects.equals`; với kiểu nguyên thủy, theo quy tắc so sánh của kiểu wrapper tương ứng.
- Mã băm kết hợp các component nhưng **thuật toán chi tiết không được bảo đảm cố định**.
- `toString` sinh chuỗi có tên record, tên component và cách biểu diễn giá trị; **đừng phân tích cú pháp chuỗi này để khôi phục dữ liệu**.

Ví dụ:

```java
record Point(int x, int y) {}

var a = new Point(3, 5);
var b = new Point(3, 5);

System.out.println(a.equals(b));                // true
System.out.println(a.hashCode() == b.hashCode()); // true
System.out.println(a);                           // Dạng thường thấy: Point[x=3, y=5]
```

Dạng chính xác của chuỗi sinh tự động không phải hợp đồng serialization ổn định. Không nên kiểm tra nguyên văn một định dạng `toString` như thể đó là schema dữ liệu lâu dài.

### 7.1. “Bất biến nông” không phải bất biến sâu

Các trường component của record là `final`, nhưng giá trị được tham chiếu có thể là một đối tượng mutable. Ví dụ, `record Holder(int[] values) {}` vẫn giữ một tham chiếu mảng có thể thay đổi.

Quan trọng hơn, `equals` được sinh cho component mảng dùng bình đẳng tham chiếu của mảng, **không tự so sánh từng phần tử**:

```java
record Holder(int[] values) {}

var a = new Holder(new int[] {1, 2});
var b = new Holder(new int[] {1, 2});

System.out.println(a.equals(b)); // false: hai mảng riêng biệt
```

Nếu muốn mảng được so sánh **theo nội dung**, cần tự thiết kế khả năng sao chép phòng vệ (*defensive copy*) và ghi đè nhất quán các phương thức.

```java
import java.util.Arrays;
import java.util.Objects;

record Bytes(byte[] data) {
    Bytes {
        data = Objects.requireNonNull(data, "data").clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Bytes that
                && Arrays.equals(data, that.data);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(data);
    }

    @Override
    public String toString() {
        return "Bytes[length=" + data.length + "]";
    }
}
```

Trong record `Bytes`, constructor sao chép dữ liệu đầu vào, accessor trả về bản sao, `equals` dùng `Arrays.equals` và `hashCode` dùng `Arrays.hashCode`. Các hành vi này cùng nhau bảo vệ giá trị nội bộ khỏi sửa đổi qua mảng gốc hoặc giá trị trả về.

Với record, đặc tả còn nêu bất biến: tạo một record mới từ các giá trị do accessor của record cũ trả về phải tạo ra record bằng record cũ. Bởi vậy, khi tùy biến accessor hoặc `equals`, cần duy trì bất biến này. Đối với `toString` của record, các record bằng nhau cũng được kỳ vọng có chuỗi biểu diễn bằng nhau (với lưu ý hiếm khi chính các giá trị component bằng nhau nhưng `toString` của chúng không nhất quán).

## 8. Lớp chứa mảng: phải ghép đúng cặp phép so sánh và hàm băm

Mảng Java kế thừa các hành vi equality/hash mặc định theo identity. Hai mảng có cùng phần tử nhưng tạo từ hai lần `new` không tự `equals` nhau.

| Kiểu dữ liệu | So sánh nội dung | Băm nội dung | Biểu diễn nội dung |
| --- | --- | --- | --- |
| Mảng một chiều, ví dụ `int[]` | `Arrays.equals(a, b)` | `Arrays.hashCode(a)` | `Arrays.toString(a)` |
| Mảng lồng nhau có kiểu tham chiếu, ví dụ `int[][]` | `Arrays.deepEquals(a, b)` | `Arrays.deepHashCode(a)` | `Arrays.deepToString(a)` |
| `String` | `a.equals(b)` hoặc `Objects.equals(a, b)` | `a.hashCode()` hoặc `Objects.hashCode(a)` | `a.toString()` / chính chuỗi đó |

```java
import java.util.Arrays;

int[] a = {1, 2, 3};
int[] b = {1, 2, 3};

System.out.println(a.equals(b));            // false
System.out.println(Arrays.equals(a, b));     // true
System.out.println(Arrays.hashCode(a)
        == Arrays.hashCode(b));             // true
System.out.println(Arrays.toString(a));      // [1, 2, 3]
```

Nếu dùng `Arrays.deepEquals` thì nên dùng `Arrays.deepHashCode` cho đúng cùng khái niệm nội dung sâu. Các hàm `deep...` không dành cho cấu trúc mảng chứa tham chiếu vòng về chính nó: tài liệu API không bảo đảm hành vi cho những cấu trúc đệ quy như vậy.

Lưu ý: một trường được khai báo `final int[]` chỉ khóa **tham chiếu**, không ngăn thay đổi phần tử mảng. Nếu trường mảng tham gia `hashCode`, đối tượng có thể gặp vấn đề khóa thay đổi trong `HashMap` dù bản thân trường được khai báo `final`.

## 9. Không sửa các thành phần dùng tính `equals` khi làm khóa băm

Một lỗi tinh vi xảy ra khi dùng **đối tượng mutable** làm khóa `HashMap`.

Xét lớp `MutableKey` có `equals` và `hashCode` dựa trên `code`:

```java
final class MutableKey {
    private String code;

    MutableKey(String code) {
        this.code = code;
    }

    void setCode(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey that
                && java.util.Objects.equals(code, that.code);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hashCode(code);
    }
}
```

Nếu dùng một instance làm khóa, sau đó gọi `setCode`, giá trị `hashCode()` của khóa có thể thay đổi. Bảng băm có thể vẫn đang tổ chức dữ liệu dựa trên mã băm cũ:

```java
var key = new MutableKey("A");
var map = new java.util.HashMap<MutableKey, String>();

map.put(key, "Value");
key.setCode("B");  // Tránh thay đổi khóa sau khi put.

String result = map.get(key); // Không còn được bảo đảm tìm thấy "Value".
```

Không nên hiểu việc tra cứu sai này là bug của `HashMap`. Vấn đề nằm ở **việc thay đổi dữ liệu định nghĩa bình đẳng trong khi đối tượng đang làm khóa**.

Cách tránh lỗi: dùng đối tượng bất biến (ví dụ lớp `final` với các thành phần bất biến hoặc record chứa component bất biến), hoặc chọn một khóa ổn định riêng như `String customerId`. Không cần đưa tất cả thuộc tính có thể thay đổi vào `equals`: chọn đúng các trường thể hiện danh tính nghiệp vụ.

Đối với một đối tượng có nhiều trường mutable, một trường `id` bất biến có thể là cơ sở bình đẳng phù hợp; nhưng cần xác định rõ trạng thái chưa có ID, ID sinh ở đâu và ID có thể thay đổi hay không. Không nên dựa vào một ID sẽ xuất hiện *sau khi* đối tượng đã được đặt vào tập hợp băm.

## 10. Kế thừa và nguy cơ phá vỡ tính đối xứng

Giả sử lớp cha `Point` xem hai đối tượng bằng nhau chỉ khi `x` và `y` bằng nhau. Lớp con `ColoredPoint` có thêm `color` và muốn so sánh cả màu.

Nếu `Point.equals` chấp nhận mọi đối tượng `instanceof Point` và so sánh tọa độ, còn `ColoredPoint.equals` yêu cầu thêm màu, có thể xảy ra:

```text
point.equals(coloredPoint) == true
coloredPoint.equals(point) == false
```

Đó là vi phạm **tính đối xứng**. Các biến thể cố sửa tình huống này bằng điều kiện phụ có thể lại phá **tính bắc cầu**.

Hai cách thiết kế thường rõ ràng hơn:

1. Với **value object** mà tập trường bình đẳng đã xác định, ưu tiên lớp `final` hoặc `record`. Không có lớp con thêm trạng thái làm thay đổi nghĩa của `equals`.
2. Nếu cần hệ phân cấp kế thừa, thiết kế quy tắc bằng nhau chung ngay từ đầu. Dùng `getClass() == other.getClass()` khi chỉ cho phép bằng nhau giữa **đúng cùng runtime class**, và xem xét tác động tới các lớp con. Với hệ phân cấp phức tạp, đừng tự kết hợp `instanceof` và trường lớp con một cách tùy tiện.

Cách `instanceof CustomerKey that` trong ví dụ đầy đủ ở trên phù hợp vì `CustomerKey` là lớp `final`. Không nên sao chép nguyên mẫu đó vào mọi lớp cha không `final` mà chưa phân tích khả năng kế thừa.

## 11. Những bẫy khác trong value equality

### 11.1. Chỉ ghi đè `equals` hoặc chỉ ghi đè `hashCode`

Nếu một lớp coi hai instance khác nhau là bằng nhau theo giá trị nhưng vẫn giữ `hashCode` theo identity mặc định của `Object`, hai instance bằng nhau **không được bảo đảm** có cùng mã băm. Đây là thiết kế vi phạm hợp đồng.

Ngược lại, chỉ ghi đè `hashCode` mà không ghi đè `equals` không tự tạo value equality: `Object.equals` vẫn so sánh identity.

### 11.2. Dùng `==` để so sánh các trường đối tượng

```java
// Không phù hợp nếu name được định nghĩa bằng nội dung String.
return this.name == that.name;
```

Hai chuỗi có nội dung giống nhau nhưng là hai instance khác nhau có thể làm phép so sánh trả về `false`. Khi trường tham gia bình đẳng theo nội dung, nên gọi `name.equals(that.name)` nếu không thể `null`, hoặc `Objects.equals(name, that.name)` nếu cho phép `null`.

### 11.3. Dữ liệu số thực và quy tắc băm

Với `double` hoặc `float`, cần xác định semantics cho `NaN` và số không có dấu. Nếu dùng `==` để so sánh trường `double` nhưng lại dùng `Double.hashCode` để băm, có thể gặp sự không nhất quán ở `+0.0` và `-0.0` (`==` coi chúng bằng nhau nhưng cách băm phân biệt). Hãy dùng một cặp quy tắc thống nhất, ví dụ `Double.compare(a, b) == 0` kết hợp `Double.hashCode(a)` khi muốn semantics tương thích với lớp wrapper.

Đối với `BigDecimal`, `compareTo` và `equals` có semantics khác nhau: `1.0` và `1.00` so sánh số học bằng nhau theo `compareTo`, nhưng `BigDecimal.equals` còn xét scale. Không nên tùy tiện thay `equals` bằng `compareTo(...) == 0` khi dữ liệu được đưa vào các cấu trúc dùng băm.

### 11.4. Trộn dữ liệu bí mật vào `toString`

```java
@Override
public String toString() {
    return "LoginRequest[userId=" + userId
            + ", token=<redacted>]";
}
```

Ý tưởng là mô tả những thuộc tính hữu ích và **che dữ liệu nhạy cảm**. Không gọi `toString` của các đối tượng chứa token, mật khẩu, dữ liệu cá nhân chỉ vì muốn log thuận tiện. Nếu cần log cấu trúc, dùng trường được cho phép theo chính sách bảo mật của hệ thống.

### 11.5. Lấy mã băm hay `toString` làm định danh lâu dài

`hashCode` không bảo đảm duy nhất, không ổn định qua các lần chạy JVM. `toString` có thể đổi định dạng khi nâng phiên bản. Nếu cần mã định danh bền vững, hãy thiết kế trường ID và quy tắc lưu trữ rõ ràng; nếu cần biểu diễn trao đổi dữ liệu, dùng format và schema riêng.

## 12. Khi nào dùng `class`, khi nào dùng `record`, khi nào giữ identity?

| Tình huống | Cách thiết kế thường phù hợp | Ghi chú |
| --- | --- | --- |
| Giá trị bất biến gồm vài thành phần, bình đẳng dựa trên tất cả thành phần | `record` | Tự có `equals`, `hashCode`, `toString` từ component. |
| Value object có bất biến, logic kiểm tra phức tạp hoặc cần lựa chọn trường bình đẳng riêng | `final class` với ba phương thức ghi đè | Chủ động định nghĩa fields, validation và định dạng biểu diễn. |
| Đối tượng có vòng đời và identity riêng, không cần value equality | Giữ `Object.equals` mặc định, hoặc định nghĩa identity nghiệp vụ rõ ràng | Không ghi đè chỉ vì “mọi lớp đều phải override”. |
| Đối tượng có mảng hoặc collection mutable | Sao chép phòng vệ / mô hình bất biến, lựa chọn hàm so sánh và băm nội dung | `record` không tự làm bất biến sâu. |
| Đối tượng dùng làm khóa của `HashMap`/phần tử `HashSet` | Giá trị bình đẳng ổn định trong thời gian nằm trong collection | Tránh sửa trường tham gia băm và equality. |
| Đối tượng chứa thông tin nhạy cảm | `toString` có chọn lọc hoặc che thông tin | Không dựa vào chuỗi sinh tự động nếu chứa secret. |

## 13. Quy trình suy nghĩ khi thiết kế hợp đồng

Khi định nghĩa một loại đối tượng mới, có thể đặt lần lượt các câu hỏi:

1. **Ý nghĩa của “bằng nhau” là gì?** Dựa trên identity phiên làm việc, mã nghiệp vụ hay nội dung?
2. **Những trường nào tham gia bình đẳng?** Các trường có thể `null`, là mảng hoặc thay đổi sau khi tạo đối tượng không?
3. **Có lớp con không?** Nếu value equality là mục tiêu và không cần kế thừa, cân nhắc `record` hoặc `final class`.
4. **Cách băm có dùng đúng cùng thông tin không?** Hai đối tượng bằng nhau phải cùng mã băm, nhưng va chạm được phép.
5. **Đối tượng có thể vào `HashMap`/`HashSet` không?** Khi có, các thành phần tham gia bình đẳng cần được giữ ổn định.
6. **`toString` hiển thị gì?** Có thể hiểu được, không `null`, không làm lộ dữ liệu nhạy cảm, và không bị ứng dụng khác dùng như định dạng trao đổi dữ liệu.
7. **Có dùng cấu trúc lồng nhau không?** Với mảng, cần `Arrays.equals`/`hashCode` hoặc cặp `deepEquals`/`deepHashCode` tương ứng.
8. **Có phù hợp với hệ thống collection khác không?** Nếu lớp còn triển khai `Comparable` hoặc được dùng với `Comparator`, suy nghĩ về sự nhất quán giữa bình đẳng và thứ tự sắp xếp.

Có thể ghi nhớ quy tắc cốt lõi bằng ba câu: **`equals` xác định thế nào là bằng nhau; `hashCode` phải tôn trọng định nghĩa đó; `toString` phải mô tả đối tượng một cách dễ đọc và an toàn.**

## 14. Tài liệu chính thức của Java 27

- [`java.lang.Object` — `equals`, `hashCode`, `toString`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Object.html): hợp đồng của ba phương thức gốc.
- [`java.util.Objects`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Objects.html): các phương thức `equals`, `hash`, `hashCode`, `toString`, `toIdentityString` và `requireNonNull`.
- [`java.lang.Record`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Record.html): semantics của các phương thức được sinh và bất biến khi sao chép record.
- [`java.util.Arrays`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Arrays.html): `equals`, `deepEquals`, `hashCode`, `deepHashCode` và cách hiển thị mảng.
- [`java.util.HashMap`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/HashMap.html): cấu trúc bảng băm, key equality và đặc tính vận hành.
- [`java.lang.String`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html): ví dụ chuẩn của value equality theo chuỗi ký tự.
- [Java Language Specification 27 — Record Classes (§8.10)](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10): cấu trúc và các phương thức implicit của record.
