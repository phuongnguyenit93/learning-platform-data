# `ByteArrayOutputStream.writeBytes(byte[])` và cách ghi mảng byte trong Java 11+

## 1. `ByteArrayOutputStream` dùng để làm gì?

`java.io.ByteArrayOutputStream` là một `OutputStream` tích lũy dữ liệu **ngay trong bộ nhớ**, vào một vùng đệm byte có thể tự mở rộng. Mỗi lần ghi, dữ liệu mới được **nối vào cuối** những byte đã có. Có thể lấy kết quả qua `toByteArray()`, xem số byte đang chứa bằng `size()`, hoặc dùng `reset()` để bắt đầu tích lũy lại.

Từ **Java 11**, lớp này có thêm phương thức:

```java
public void writeBytes(byte[] b)
```

Phương thức nhận **một mảng `byte[]`** và ghi **toàn bộ byte** của mảng vào cuối bộ đệm. API này vẫn tồn tại và được hỗ trợ trên các JDK hiện đại.

Ví dụ ngắn:

```java
ByteArrayOutputStream output = new ByteArrayOutputStream();
output.writeBytes(new byte[] {1, 2, 3});
output.writeBytes(new byte[] {4, 5});
// output.toByteArray() chứa [1, 2, 3, 4, 5].
```

Đoạn trên minh họa API và cần `import java.io.ByteArrayOutputStream;` khi đưa vào chương trình hoàn chỉnh. `writeBytes` **không tự thêm dấu phân cách**, **không chuyển byte thành ký tự**, **không tạo tệp** và **không gửi dữ liệu ra mạng**: nó chỉ tích lũy các byte đã cung cấp vào bộ đệm trong RAM.

## 2. `writeBytes` hoạt động như thế nào?

Theo hợp đồng API, lời gọi:

```java
output.writeBytes(data);
```

tương đương về hành vi ghi với:

```java
output.write(data, 0, data.length);
```

Trong đó:

- `data` là mảng nguồn không được `null`.
- Vị trí `0` là byte đầu tiên cần lấy trong mảng.
- `data.length` là **số byte** cần ghi. Toàn bộ mảng được nối vào cuối dữ liệu đã tích lũy.
- `writeBytes` trả về `void`. Nó **không khai báo checked exception `IOException`**; nhưng vẫn có thể ném ngoại lệ runtime, chẳng hạn `NullPointerException` khi nhận `null`.

Điểm quan trọng: `writeBytes` **sao chép các byte** vào bộ đệm. Thay đổi mảng đầu vào **sau khi ghi** không làm thay đổi những byte đã ghi. `toByteArray()` lại tạo một **mảng mới** chứa bản sao phần dữ liệu hợp lệ; sửa mảng kết quả cũng không sửa bộ đệm bên trong.

Vì vùng đệm tự tăng khi cần, không phải tự tạo trước mảng có kích thước chính xác. Tuy nhiên, bộ nhớ dùng cho bộ đệm và các bản sao vẫn tăng theo tổng dữ liệu tích lũy.

## 3. Phân biệt các cách ghi byte

| Cách gọi trên biến kiểu `ByteArrayOutputStream` | Ý nghĩa | Checked `IOException` ở chữ ký phương thức được gọi |
| --- | --- | --- |
| `out.writeBytes(byte[] bytes)` | Ghi **toàn bộ** mảng byte; API có từ Java 11 | **Không** |
| `out.write(byte[] bytes, int offset, int length)` | Ghi `length` byte bắt đầu từ `offset` | **Không**, vì `ByteArrayOutputStream` override phương thức này |
| `out.write(int value)` | Ghi một byte, lấy **8 bit thấp** của `value` | **Không**, vì `ByteArrayOutputStream` override phương thức này |
| `out.write(byte[] bytes)` | Ghi toàn bộ mảng theo phương thức kế thừa từ `OutputStream` | **Có**: chữ ký `OutputStream.write(byte[])` khai báo `throws IOException` |

Dòng cuối là một chi tiết Java thường gây bất ngờ: `ByteArrayOutputStream` **không override** `write(byte[])` riêng, nên lời gọi một đối số này vẫn sử dụng chữ ký kế thừa có `throws IOException`, mặc dù đích thực tế là bộ đệm trong RAM. Nếu viết mã:

```java
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.write(new byte[] {1, 2, 3});
```

thì phương thức chứa lời gọi phải **xử lý hoặc khai báo `IOException`**. Ngược lại, hai cách sau không đòi xử lý checked `IOException` khi biến được khai báo là `ByteArrayOutputStream`:

```java
out.writeBytes(new byte[] {1, 2, 3});   // Java 11+
out.write(new byte[] {1, 2, 3}, 0, 3);  // Các Java hiện đại
```

Nếu biến chỉ được khai báo bằng kiểu cha `OutputStream`, các phương thức thấy được và checked exceptions dựa vào **kiểu tĩnh** ấy; `writeBytes` không phải phương thức của `OutputStream`. Không thể gọi `writeBytes` trên một biến chỉ có kiểu `OutputStream` mà không đổi thiết kế hoặc kiểm tra/ép kiểu phù hợp.

## 4. Ví dụ Java hoàn chỉnh và kết quả chạy chính xác

Tạo tệp **`WriteBytesDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class WriteBytesDemo {
    public static void main(String[] args) {
        byte[] first = "Java".getBytes(StandardCharsets.UTF_8);
        byte[] second = " 11".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.writeBytes(first);
        out.writeBytes(second);

        System.out.println("text=" + out.toString(StandardCharsets.UTF_8));
        System.out.println("size=" + out.size());

        first[0] = (byte) 'X';
        System.out.println("afterInputChange=" +
                out.toString(StandardCharsets.UTF_8));

        byte[] snapshot = out.toByteArray();
        snapshot[0] = (byte) 'Y';
        System.out.println("snapshot=" +
                new String(snapshot, StandardCharsets.UTF_8));
        System.out.println("original=" +
                out.toString(StandardCharsets.UTF_8));

        byte[] numbers = {10, 20, 30, 40};
        out.write(numbers, 1, 2);
        System.out.println("bytes=" + Arrays.toString(out.toByteArray()));
        System.out.println("afterRangeSize=" + out.size());

        out.reset();
        out.writeBytes("Chào".getBytes(StandardCharsets.UTF_8));
        System.out.println("afterReset=" +
                out.toString(StandardCharsets.UTF_8));
        System.out.println("utf8ByteCount=" + out.size());
    }
}
```

Lệnh chạy với **JDK 17+** (chương trình cũng dùng được từ Java 11):

```bash
javac WriteBytesDemo.java
java WriteBytesDemo
```

**Stdout chính xác**:

```text
text=Java 11
size=7
afterInputChange=Java 11
snapshot=Yava 11
original=Java 11
bytes=[74, 97, 118, 97, 32, 49, 49, 20, 30]
afterRangeSize=9
afterReset=Chào
utf8ByteCount=5
```

Cách đọc kết quả:

1. `first` chứa 4 byte UTF-8 (`Java`), `second` chứa 3 byte (` 11`), nên sau hai lần `writeBytes`, chuỗi giải mã là `Java 11` và `size() == 7`.
2. Khi đổi `first[0]` thành `'X'`, bộ đệm vẫn giữ `Java 11`: dữ liệu đầu vào đã được **sao chép** khi ghi.
3. `toByteArray()` trả về bản sao. Đổi `snapshot[0]` thành `'Y'` chỉ khiến bản sao hiển thị `Yava 11`, còn `out` vẫn là `Java 11`.
4. `out.write(numbers, 1, 2)` chỉ nối `20, 30` (hai phần tử bắt đầu từ chỉ số 1), khiến tổng độ dài tăng từ 7 lên 9 byte. Dãy số `74, 97, 118, 97, 32, 49, 49` là mã byte ASCII/UTF-8 của `Java 11`.
5. `reset()` làm kích thước dữ liệu hợp lệ trở về 0 để tái sử dụng bộ đệm. Sau đó `writeBytes` ghi `Chào` dưới dạng UTF-8. Chuỗi có **4 ký tự Java** nhưng được biểu diễn bằng **5 byte UTF-8**, nên `utf8ByteCount=5`.

## 5. Ghi toàn bộ mảng hay chỉ một đoạn mảng?

Giả sử một giao thức có mảng dữ liệu `payload` chứa 5 byte, nhưng chỉ muốn lấy 3 byte ở giữa:

```java
byte[] payload = {10, 20, 30, 40, 50};
ByteArrayOutputStream out = new ByteArrayOutputStream();

out.writeBytes(payload);       // Kết quả: [10, 20, 30, 40, 50].
out.reset();

out.write(payload, 1, 3);      // Kết quả: [20, 30, 40].
```

Đây là một **đoạn minh họa** trong chương trình có import `java.io.ByteArrayOutputStream`. Không có overload `writeBytes(byte[], offset, length)` trong API `ByteArrayOutputStream`. Khi chỉ ghi một đoạn, dùng `write(byte[], int, int)`.

Đối với `write(payload, off, len)`:

- `off` là chỉ số bắt đầu, đếm từ 0.
- `len` là **số byte**, không phải chỉ số kết thúc.
- `off` và `len` phải không âm, đồng thời `len` không được lớn hơn `payload.length - off`. Vi phạm gây `IndexOutOfBoundsException`.
- `payload == null` gây `NullPointerException`. Nếu `len == 0` với mảng hợp lệ và `off` hợp lệ, không có byte nào được ghi.

Nhờ cách phân biệt này, một mảng làm bộ đệm dùng chung có thể chứa phần dữ liệu chưa sử dụng; lập trình viên chỉ ghi các byte thực sự có ý nghĩa, thay vì vô tình đưa cả vùng trống vào đầu ra.

## 6. Chuỗi và byte: chỉ rõ encoding

`writeBytes` **không nhận `String`** và không mã hóa văn bản. Muốn tích lũy văn bản, hãy quyết định bảng mã rồi chuyển thành byte trước khi ghi:

```java
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.writeBytes("Xin chào".getBytes(StandardCharsets.UTF_8));

byte[] encoded = out.toByteArray();
String decoded = out.toString(StandardCharsets.UTF_8);
```

Đoạn này minh họa API và cần import `ByteArrayOutputStream`, `StandardCharsets`. Ở đây `encoded` chứa byte UTF-8; `decoded` là chuỗi `"Xin chào"`.

Nên dùng `StandardCharsets.UTF_8` nhất quán ở hai đầu nếu dữ liệu cần biểu diễn tiếng Việt và trao đổi giữa hệ thống. **Không suy ra số byte từ `String.length()`**: một ký tự Unicode có thể dùng nhiều byte UTF-8, và số phần tử `byte[]` là số byte thực tế. Nếu dữ liệu là ảnh, tệp ZIP, mã hóa nhị phân hoặc giao thức mạng, giữ chúng dưới dạng `byte[]`; không cố biến thành `String` để ghi.

Lưu ý tên phương thức: `ByteArrayOutputStream.writeBytes(byte[])` **khác** `DataOutputStream.writeBytes(String)`. Chúng thuộc hai lớp khác nhau, nhận hai loại dữ liệu khác nhau và có quy tắc ghi khác nhau. Không chọn API chỉ vì trùng tên `writeBytes`.

## 7. Trường hợp biên và ngoại lệ

**Mảng rỗng:** `out.writeBytes(new byte[0])` hợp lệ và không thêm byte nào. `size()` không đổi.

**Mảng `null`:**

```java
out.writeBytes(null); // Biên dịch được nhưng ném NullPointerException khi chạy.
```

Đây là lỗi runtime do đầu vào không hợp lệ; không có chuyện `null` được hiểu thành mảng rỗng.

**Ghi lỗi do bộ nhớ:** `ByteArrayOutputStream` lưu toàn bộ dữ liệu trong RAM; với dữ liệu rất lớn, vùng đệm và các bản sao `toByteArray()` có thể gây áp lực bộ nhớ hoặc `OutOfMemoryError`. Nếu dữ liệu quá lớn hoặc phải xử lý liên tục, ưu tiên xử lý theo từng khối tới một `OutputStream` thật (tệp, mạng...) hoặc một API streaming thích hợp thay vì luôn gom toàn bộ vào RAM.

**Đóng bộ đệm:** `close()` trên `ByteArrayOutputStream` không có tác dụng đối với nội dung và các phương thức vẫn sử dụng được sau khi gọi `close()`. Không cần `close()` để “đẩy” dữ liệu ra tệp; muốn gửi nội dung tới một `OutputStream` khác có thể dùng `writeTo(target)` hoặc `target.write(out.toByteArray())`. Với đích là file/socket, thao tác thật có thể ném `IOException` và cần xử lý tài nguyên của **đích**.

**`toByteArray()` tạo bản sao:** gọi nhiều lần trên bộ đệm lớn có thể tốn thời gian và bộ nhớ. Khi chỉ cần đếm byte, dùng `size()`; khi muốn chuyển nội dung sang `OutputStream` khác, cân nhắc `writeTo(target)` để tránh tự tạo một bản sao trung gian không cần thiết.

## 8. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `writeBytes` ghi ra file | Nó nối dữ liệu vào `ByteArrayOutputStream` trong bộ nhớ. Muốn ghi file, sử dụng stream/file API phù hợp. |
| `writeBytes` tự chuyển `String` thành byte | Phương thức nhận `byte[]`; hãy mã hóa `String` bằng charset rõ ràng trước. |
| `writeBytes` thay thế toàn bộ byte cũ | Phương thức **nối thêm**. Dùng `reset()` nếu thực sự muốn bắt đầu lại. |
| `writeBytes` và `write(b, off, len)` giống nhau mọi trường hợp | `writeBytes` luôn ghi **toàn bộ** mảng; `write` ba tham số ghi được **một đoạn**. |
| `toByteArray()` trả mảng nội bộ có thể sửa trực tiếp | Nó trả một **bản sao mới**; sửa bản sao không tác động bộ đệm. |
| `size()` cho biết số ký tự | `size()` đếm **byte**, không đếm ký tự Unicode. |
| `out.write(byte[])` trên `ByteArrayOutputStream` không cần bắt checked exception | Phương thức một đối số `write(byte[])` được kế thừa từ `OutputStream`, nên chữ ký vẫn có `throws IOException`. Dùng `writeBytes(byte[])` nếu muốn API chuyên biệt Java 11+. |

## 9. Bài tập tự kiểm tra

Giả sử:

```java
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.writeBytes(new byte[] {1, 2});
out.writeBytes(new byte[] {3});
out.write(new byte[] {4, 5, 6}, 1, 2);
```

**Câu 1.** `Arrays.toString(out.toByteArray())` là gì?

**Đáp án:** `[1, 2, 3, 5, 6]`: hai lần `writeBytes` nối 1, 2, 3; lời gọi `write` cuối chỉ lấy 5, 6.

**Câu 2.** `out.size()` bằng bao nhiêu?

**Đáp án:** `5` byte.

**Câu 3.** Nếu thực hiện `out.reset(); out.writeBytes(new byte[] {9});`, kết quả là gì?

**Đáp án:** `[9]` và `size() == 1`.

**Câu 4.** Đưa một đoạn nhỏ của mảng vào stream thì nên dùng cách nào?

**Đáp án:** `out.write(array, offset, length)`. Nếu cần ghi toàn bộ mảng thì dùng `out.writeBytes(array)`.

**Ghi nhớ:** `ByteArrayOutputStream.writeBytes(byte[])` (Java 11+) giúp **nối toàn bộ một mảng byte** vào bộ đệm trong RAM, tương đương `write(b, 0, b.length)`, không khai báo checked `IOException`. Dùng `write(byte[], off, len)` khi cần ghi một đoạn; dùng `toByteArray()` để lấy bản sao dữ liệu; dùng `StandardCharsets.UTF_8` khi có chuyển đổi văn bản.

**Tham khảo API chính thức:** [Oracle Java SE 11 — `ByteArrayOutputStream`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/ByteArrayOutputStream.html) và [Oracle Java SE 25 — `ByteArrayOutputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ByteArrayOutputStream.html).
