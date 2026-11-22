# Nhiều giới hạn và thứ tự lớp, giao diện trong intersection bound

## 1. Một tham số kiểu cần đồng thời nhiều khả năng

Một phương thức generic có thể cần nhiều hơn một khả năng từ cùng đối tượng: đọc thông tin do lớp cơ sở cung cấp, thực hiện công việc qua `Runnable` và đóng tài nguyên qua `Closeable`. Chỉ một giới hạn riêng lẻ không diễn đạt đủ hợp đồng đó.

**Giới hạn giao (intersection bound)** kết hợp nhiều giới hạn trên bằng dấu `&`:

```java
static <T extends NamedResource & Runnable & java.io.Closeable>
void process(T resource) throws java.io.IOException {
    try (resource) {
        System.out.println(resource.name());
        resource.run();
    }
}
```

Đoạn khai báo minh họa này cần một lớp `NamedResource` có phương thức `name()` phù hợp; chương trình đầy đủ xuất hiện ở phần sau. `T` phải đồng thời là kiểu con của `NamedResource`, `Runnable` và `Closeable`. Cùng một đối tượng đáp ứng cả ba yêu cầu.

```text
                 T
               / | \
              /  |  \
 NamedResource Runnable Closeable
    name()       run()   close()
```

Dấu `&` ở đây mang nghĩa **đồng thời thỏa tất cả**, không phải chọn một trong các kiểu. Đó là ràng buộc ở thời điểm biên dịch, không phải một chuỗi thao tác thử kiểu khi chạy.

Bài này dùng kiến thức còn áp dụng trong Java hiện hành. Các ví dụ hoàn chỉnh chạy với Java 17 trở lên; `Closeable` là giao diện hiện hành dành cho tài nguyên có thao tác đóng, với `close()` có thể ném `IOException`.

## 2. Cú pháp: một extends, nhiều giới hạn nối bằng &

Dạng thường gặp:

```text
<T extends LớpCơSở & GiaoDiện1 & GiaoDiện2>
```

Hoặc chỉ có các giao diện:

```text
<T extends GiaoDiện1 & GiaoDiện2>
```

Hai dòng trên là sơ đồ cú pháp, không phải mã Java có thể chạy. Các điểm cần phân biệt:

- Dùng **một** từ khóa `extends` để bắt đầu giới hạn.
- Dùng `&` để nối các giới hạn của **cùng một tham số kiểu**.
- Dùng dấu phẩy để phân cách **các tham số kiểu khác nhau**.
- Trong khai báo giới hạn, vẫn dùng `extends` khi các giới hạn là giao diện; không dùng `implements`.

Ví dụ sau là các dạng khai báo minh họa:

```java
// Một tham số kiểu, hai khả năng:
// <T extends Runnable & java.io.Closeable>

// Hai tham số kiểu độc lập, mỗi tham số có giới hạn riêng:
// <A extends Runnable, B extends java.io.Closeable>
```

Dạng thứ hai không khẳng định một đối tượng duy nhất vừa chạy vừa đóng được. Nó khai báo `A` và `B` độc lập; các đối số có thể thuộc hai kiểu khác nhau.

Không dùng `|` thay `&`. Dấu `|` trong multi-catch biểu thị lựa chọn giữa loại ngoại lệ; nó không phải cú pháp giới hạn trên cho tham số kiểu.

## 3. Nếu có lớp, lớp phải đứng đầu

Các giới hạn sau dấu `&` phải là kiểu giao diện. Vì vậy, nếu giới hạn chứa một lớp thì lớp đó phải đứng trước mọi giao diện, và chỉ có tối đa một lớp.

| Dạng | Hợp lệ? | Lý do |
| --- | --- | --- |
| `<T extends Number & Comparable<T>>` | Có | Lớp `Number` đứng đầu; tiếp theo là giao diện |
| `<T extends Runnable & java.io.Closeable>` | Có | Cả hai đều là giao diện |
| `<T extends java.io.Closeable & Runnable>` | Có | Đổi thứ tự hai giao diện vẫn hợp lệ |
| `<T extends Comparable<T> & Number>` | Không | Lớp `Number` không được đứng sau `&` |
| `<T extends Number & String>` | Không | Không được có hai giới hạn lớp |
| `<T extends Runnable implements java.io.Closeable>` | Không | Không dùng `implements` trong giới hạn tham số kiểu |

Quy tắc này áp dụng cho **vị trí của kiểu trong danh sách giới hạn**, không phụ thuộc lớp đứng đầu có phải lớp trừu tượng hay không. `Number` là lớp trừu tượng nhưng vẫn là một kiểu lớp.

Không cần thêm `Object` chỉ để “có lớp đứng đầu”. `<T extends Runnable & Closeable>` đã diễn đạt đầy đủ hai khả năng. Thêm `Object &` còn có thể thay đổi kiểu sau xóa kiểu, nên không nên xem đó là phần trang trí vô hại.

## 4. Phần thân phương thức thấy được gì?

Một biến kiểu có nhiều giới hạn cho phép dùng các thành viên có thể truy cập thông qua giao của những giới hạn đó. Trong ví dụ đầu bài:

- `NamedResource` cung cấp `name()`.
- `Runnable` cung cấp `run()`.
- `Closeable` cung cấp `close()`, vì thế đối tượng dùng được trong try-with-resources.

Không cần ép `resource` riêng sang `Runnable` để gọi `run()`. Trình biên dịch đã có bảo đảm về khả năng ấy từ giới hạn khai báo.

Giới hạn không bỏ qua mức truy cập: không thể gọi một phương thức `private` của lớp cơ sở chỉ vì lớp đó xuất hiện trong bound. Các quy tắc truy cập vẫn áp dụng tại nơi khai báo phương thức generic.

Giới hạn cũng không loại bỏ ngoại lệ có kiểm tra. `Closeable.close()` có thể ném `IOException`; phương thức `process` cần bắt hoặc khai báo ngoại lệ phù hợp. Nếu dùng `AutoCloseable` trực tiếp, hợp đồng `close()` rộng hơn và có thể yêu cầu xử lý `Exception`, không mặc nhiên chỉ là `IOException`.

## 5. Chương trình chạy đầy đủ

Lưu toàn bộ mã sau thành **`IntersectionBoundsDemo.java`**. Tài nguyên trong ví dụ là mô hình giả lập ghi ra stdout; nó không mở tệp hay kết nối mạng.

```java
import java.io.Closeable;
import java.io.IOException;

abstract class NamedResource {
    private final String name;

    protected NamedResource(String name) {
        this.name = name;
    }

    public final String name() {
        return name;
    }
}

final class ReportResource extends NamedResource
        implements Runnable, Closeable {
    ReportResource(String name) {
        super(name);
    }

    @Override
    public void run() {
        System.out.println("run=" + name());
    }

    @Override
    public void close() {
        System.out.println("close=" + name());
    }
}

public class IntersectionBoundsDemo {
    static <T extends NamedResource & Runnable & Closeable>
    void process(T resource) throws IOException {
        try (resource) {
            System.out.println("name=" + resource.name());
            resource.run();
        }
    }

    static <T extends Number & Comparable<T>> T larger(T first, T second) {
        return first.compareTo(second) >= 0 ? first : second;
    }

    public static void main(String[] args) throws IOException {
        process(new ReportResource("monthly"));
        Integer result = larger(4, 9);
        System.out.println("larger=" + result);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all IntersectionBoundsDemo.java
java IntersectionBoundsDemo
```

Stdout chính xác:

```text
name=monthly
run=monthly
close=monthly
larger=9
```

`ReportResource` đáp ứng đủ ba giới hạn của `process` thông qua lớp cơ sở và các giao diện được triển khai. Try-with-resources gọi `close()` khi kết thúc khối. Giới hạn kiểu không tự gọi `close`; chính cấu trúc try-with-resources tạo ra hành vi quản lý tài nguyên.

Phương thức `larger` minh họa một giới hạn chứa giao diện generic: `Comparable<T>` cho phép so sánh với giá trị cùng kiểu `T`, còn kiểu trả về `T` giữ thông tin kiểu ở bên gọi. Với hai đối số `Integer`, kết quả được nhận trực tiếp bằng biến `Integer`.

`Number` có mặt vì hợp đồng minh họa này cố ý chỉ nhận miền số. Nếu thuật toán chỉ cần so sánh các giá trị bất kỳ, không nên yêu cầu thêm `Number` khi không có lý do nghiệp vụ. Một API so sánh tổng quát hơn cũng thường cân nhắc `Comparable<? super T>` để chấp nhận thêm các quan hệ kế thừa phù hợp; việc chọn dạng đó độc lập với quy tắc lớp đứng đầu.

## 6. Đáp ứng giới hạn phải được chứng minh từ kiểu tĩnh

Giả sử có đối tượng đúng lớp như trong chương trình:

```java
ReportResource report = new ReportResource("daily");
process(report); // Hợp lệ trong lớp có phương thức process.
```

Nếu cùng đối tượng được giữ qua một biến chỉ có kiểu `Runnable`, lời gọi không còn đủ dữ kiện:

```java
Runnable runnable = new ReportResource("daily");
// process(runnable); // Lỗi biên dịch.
```

Lớp thực tế vẫn có thể đóng được và có `name()`, nhưng kiểu tĩnh `Runnable` không chứng minh được hai khả năng còn lại. Suy luận kiểu không tự kiểm tra đối tượng khi chạy để bổ sung giới hạn còn thiếu.

Ngược lại, một lớp đáp ứng một giới hạn nhưng thiếu giới hạn khác không thể được truyền vào chỉ vì phương thức trong một nhánh thực thi không dùng tới khả năng bị thiếu. Giới hạn là hợp đồng của toàn bộ lời gọi.

`null` vẫn có thể phù hợp về kiểu với tham số tham chiếu có nhiều giới hạn. Bound không bảo đảm khác `null`; chương trình cần chính sách kiểm tra dữ liệu riêng. Không dùng một lời gọi với `null` làm bằng chứng rằng đã có một đối tượng đáp ứng và thực hiện được mọi thao tác.

## 7. Thứ tự các giao diện ảnh hưởng đến xóa kiểu

Khi chỉ có các giao diện, có thể đảo thứ tự nếu các giới hạn khác vẫn hợp lệ:

```java
class ErasureOrder {
    static <T extends Runnable & java.io.Closeable>
    void runnableFirst(T resource) {
        resource.run();
    }

    static <T extends java.io.Closeable & Runnable>
    void closeableFirst(T resource) {
        resource.run();
    }
}
```

Đây là một tệp độc lập tên **`ErasureOrder.java`**. Cả hai phương thức đều yêu cầu cùng hai khả năng, và cả hai đều gọi được `run()` mà không ép kiểu trong mã nguồn.

Tuy nhiên, **kiểu sau xóa kiểu (erasure) của tham số kiểu được quyết định bởi giới hạn đứng đầu**:

| Tham số kiểu | Kiểu sau xóa kiểu của `T` |
| --- | --- |
| `<T extends Runnable & Closeable>` | `Runnable` |
| `<T extends Closeable & Runnable>` | `Closeable` |
| `<T extends NamedResource & Runnable & Closeable>` | `NamedResource` |
| `<T extends Number & Comparable<T>>` | `Number` |

Có thể kiểm tra descriptor của bytecode bằng các công cụ trong JDK:

```shell
javac --release 17 ErasureOrder.java
javap -s ErasureOrder
```

Các descriptor đáng chú ý trong kết quả:

```text
runnableFirst: (Ljava/lang/Runnable;)V
closeableFirst: (Ljava/io/Closeable;)V
```

Hai dòng trên ghép tên phương thức với descriptor để dễ đối chiếu; `javap` thực tế in khai báo phương thức và dòng `descriptor:` riêng. `V` trong descriptor biểu thị `void`.

Giới hạn đứng đầu không phải “khả năng được ưu tiên” và không làm các giới hạn khác mất hiệu lực khi kiểm tra mã nguồn. Nhưng thay đổi thứ tự trong API đã biên dịch có thể thay đổi descriptor của phương thức, ảnh hưởng đến mã gọi đã được biên dịch trước đó. Vì vậy, không đổi thứ tự bound trong thư viện công khai chỉ vì xem nó là chỉnh định dạng.

## 8. Các giới hạn kết hợp phải tương thích

### Không lặp cùng một giao diện theo các đối số kiểu khác nhau

```java
// Không hợp lệ:
// <T extends Comparable<String> & Comparable<Integer>>
```

Hai thành phần có cùng kiểu sau xóa kiểu là `Comparable`. Một biến kiểu cũng không được đồng thời là kiểu con của hai cách tham số hóa khác nhau của cùng một giao diện generic, kể cả xung đột xuất hiện qua các nhánh kế thừa.

Ví dụ minh họa gián tiếp:

```java
interface TextComparable extends Comparable<String> {
}

interface NumberComparable extends Comparable<Integer> {
}

// Không hợp lệ dù hai tên giao diện trực tiếp khác nhau:
// <T extends TextComparable & NumberComparable>
```

Hai giao diện riêng lẻ có thể khai báo được, nhưng kết hợp chúng làm một bound dẫn đến yêu cầu `Comparable` mâu thuẫn. Đừng sửa bằng cách bỏ đối số kiểu hoặc ép kiểu không được kiểm tra.

### Thành viên được thừa kế không được tạo mâu thuẫn

Nếu hai giao diện yêu cầu cùng một chữ ký phương thức nhưng có kiểu trả về không tương thích, việc kết hợp có thể không hợp lệ. Dấu `&` không tự giải quyết xung đột hợp đồng. Cần sửa thiết kế các giao diện hoặc chọn các khả năng thực sự kết hợp được.

### Không nối thêm giới hạn sau một biến kiểu

Một giới hạn có thể là một biến kiểu khác đứng riêng:

```java
// Hợp lệ về dạng khai báo:
// <U, T extends U>

// Không hợp lệ:
// <U, T extends U & Runnable>
```

Trong cú pháp bound của tham số kiểu, nếu giới hạn bắt đầu bằng một **biến kiểu** như `U`, đó là dạng giới hạn đơn; không được nối thêm các giao diện bằng `&` ở sau. Quy tắc “lớp hoặc biến kiểu chỉ đứng đầu” không nên bị diễn giải thành việc luôn có thể thêm `&` sau mọi biến kiểu.

## 9. Những điều intersection bound không làm

- Không tạo một lớp mới tên `NamedResource & Runnable & Closeable` để khởi tạo bằng `new`.
- Không cho phép Java kế thừa nhiều lớp. Lớp thực tế vẫn tuân theo quy tắc một lớp cha trực tiếp.
- Không tự cấp quyền truy cập thành viên `private`, không tự bắt ngoại lệ, không tự kiểm tra `null`.
- Không phải cú pháp tùy ý dùng được ở mọi vị trí ghi kiểu: không viết `List<? extends Number & Runnable>` để ghép nhiều giới hạn wildcard trực tiếp theo cách này.
- Không tự làm dữ liệu bất biến hoặc an toàn đa luồng; các giới hạn chỉ bảo đảm những quan hệ kiểu đã khai báo.

Khi nhiều nơi đều cần cùng một bộ giao diện và bộ khả năng đó có tên nghiệp vụ rõ ràng, có thể khai báo một giao diện chung kế thừa các giao diện thành phần. Intersection bound hữu ích khi cần diễn đạt các yêu cầu kết hợp ngay tại thao tác generic, đặc biệt khi các kiểu có sẵn không cùng một giao diện nghiệp vụ được đặt tên trước.

## 10. Tự thực hành

1. Trong chương trình đầy đủ, thử đổi thành `Runnable & NamedResource & Closeable` và quan sát lỗi vì lớp không đứng đầu. Khôi phục trước khi chạy.
2. Tạo một lớp chỉ kế thừa `NamedResource` và thực hiện `Runnable`, nhưng không thực hiện `Closeable`. Giải thích vì sao không gọi được `process` với nó.
3. Biên dịch `ErasureOrder.java`, chạy `javap -s` và đối chiếu hai descriptor. Phân biệt yêu cầu ở mã nguồn với biểu diễn tham số sau xóa kiểu.
4. Truyền hai `Double` vào `larger`; xác nhận kiểu kết quả có thể là `Double`. Thử hai chuỗi và giải thích giới hạn `Number` khiến lời gọi bị từ chối.
5. Phân biệt `<A extends Runnable, B extends Closeable>` với `<T extends Runnable & Closeable>` bằng số tham số kiểu và số khả năng mà một kiểu cụ thể phải đáp ứng.

Khi đọc một intersection bound, hãy xác định: các khả năng nào phải có đồng thời, có lớp nào cần đứng đầu, các giao diện có tương thích nhau không và giới hạn đầu tiên sẽ trở thành kiểu gì sau xóa kiểu. Bốn câu hỏi đó giúp kiểm tra cả tính hợp lệ của mã nguồn lẫn tác động khi thay đổi API.

## Tài liệu đối chiếu

- [JLS §4.4 — Type Variables](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.4): dạng giới hạn, thứ tự, thành viên và các điều kiện hợp lệ.
- [JLS §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6): xóa kiểu theo giới hạn đứng đầu.
- [JLS §4.9 — Intersection Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.9): quan hệ với kiểu giao.
- [AutoCloseable — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng đóng tài nguyên và try-with-resources.
