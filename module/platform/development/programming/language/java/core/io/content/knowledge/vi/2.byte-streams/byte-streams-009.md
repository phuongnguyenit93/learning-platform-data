# `InputStream.transferTo` và quyền sở hữu hai stream

Khi sao chép byte từ một nguồn sang một đích, Java cung cấp `InputStream.transferTo(OutputStream)` để đọc toàn bộ **phần dữ liệu còn lại** của luồng đầu vào và ghi lần lượt sang luồng đầu ra. Phương thức này giúp code sao chép ngắn gọn, nhưng có một quy tắc dễ bỏ sót: **`transferTo` không đóng cả hai stream**. Việc đóng tài nguyên thuộc trách nhiệm của bên sở hữu chúng.

Bài học tập trung vào hai câu hỏi: **`transferTo` thực sự làm gì với dữ liệu?** và **ai phải đóng input/output sau lời gọi đó?**

## 1. API và cơ chế của `transferTo`

Kể từ **Java 9**, lớp `java.io.InputStream` có phương thức:

~~~java
public long transferTo(OutputStream out) throws IOException
~~~

Gọi bằng:

~~~java
long count = input.transferTo(output);
~~~

Ý nghĩa:

- **`input`** là `InputStream` đang ở vị trí đọc hiện tại. Nó là nguồn của thao tác.
- **`output`** là `OutputStream` nhận các byte. Nó là đích của thao tác.
- Phương thức đọc lần lượt các byte còn lại từ `input` và ghi chúng vào `output` **theo cùng thứ tự**.
- Khi trả về thành công, `input` đã ở **cuối luồng** (end of stream); một lần đọc tiếp thường sẽ nhận dấu hiệu hết luồng `-1` nếu lớp luồng tuân theo ngữ nghĩa EOF thông thường.
- Kết quả trả về kiểu `long` là **số byte đã chuyển**, không phải chuỗi, không phải mảng byte và không phải số ký tự.
- `transferTo` **không gọi `close()` trên `input` hoặc `output`** theo hợp đồng API. Sau khi chuyển xong, chúng vẫn thuộc bên chịu trách nhiệm quản lý.
- Nếu `output` bằng `null`, phương thức ném `NullPointerException`. Nếu thao tác đọc/ghi gặp lỗi, nó có thể ném `IOException` **sau khi đã chuyển một phần dữ liệu**.

Sơ đồ dòng dữ liệu:

~~~text
                      InputStream.transferTo(OutputStream)
Tệp / socket / memory -------- [đọc byte -> ghi byte] --------> Tệp / socket / memory
      input (nguồn)                                             output (đích)
      đã tới EOF nếu thành công                                   không tự đóng
       không tự đóng                                             không tự flush bảo đảm
~~~

Điểm quan trọng là **`transferTo` thực hiện sao chép byte**, không tự chuyển mã ký tự, không xử lý văn bản và không cần bạn tự tạo `byte[]` để viết vòng lặp thông thường. Nội dung truyền có thể là văn bản UTF-8, ảnh, ZIP hay dữ liệu nhị phân bất kỳ.

Ví dụ, với luồng đang chứa `A B C D E` nhưng đã đọc trước `A B`, gọi `transferTo` sẽ chuyển **`C D E`**, vì nó hoạt động từ **vị trí hiện tại**; không quay lại đầu luồng. Với nguồn đã hết dữ liệu, kết quả là `0`.

### So với vòng lặp `read`/`write`

Công việc về mặt ý nghĩa gần tương đương:

~~~java
byte[] buffer = new byte[8192];
long total = 0;
int n;
while ((n = input.read(buffer)) != -1) {
    output.write(buffer, 0, n);
    total += n;
}
~~~

Trong đoạn này, phải ghi đúng `n` byte vừa đọc vì `read(buffer)` không bắt buộc lấp đầy mảng. `transferTo` che giấu việc lặp và quản lý bộ đệm trong triển khai. Đừng kết luận từ đó rằng mọi `InputStream` cụ thể đều có cùng chiến lược tối ưu; lớp con có thể thay đổi triển khai.

Với API Java I/O, **đọc đến EOF không tương đương với đóng stream**: một luồng đọc có thể đã cạn nhưng vẫn chưa được `close` và vẫn có thể giữ tài nguyên như file descriptor hoặc kết nối.

## 2. Quyền sở hữu stream là gì?

**Quyền sở hữu (ownership)** là trách nhiệm quyết định khi nào một tài nguyên được đóng hoặc giải phóng. Trong code Java, bản thân kiểu `InputStream` hay `OutputStream` **không cho biết chắc** ai sở hữu: điều này đến từ cách tạo stream và **hợp đồng giữa các phương thức**.

Có ba vai trò thường gặp:

1. **Bên tạo và sở hữu stream:** ví dụ phương thức tự gọi `Files.newInputStream(path)` và `Files.newOutputStream(path)` để thực hiện công việc. Thông thường nó chịu trách nhiệm đóng cả hai stream.
2. **Bên mượn stream (borrower):** ví dụ helper nhận tham số `InputStream input, OutputStream output` do caller truyền vào. Mặc định helper chỉ sử dụng chúng; caller tiếp tục quản lý vòng đời. Nếu API muốn nhận quyền sở hữu, phải nói rõ trong hợp đồng.
3. **Bên quản lý vòng đời ở cấp cao hơn:** ví dụ framework quản lý request/response, kết nối mạng, hoặc `System.in`/`System.out` do môi trường chạy cung cấp. Code dùng một lần không nên tự ý đóng tài nguyên chung.

Quy tắc thiết kế thực dụng: **nơi sở hữu tài nguyên đóng tài nguyên; nơi chỉ mượn không đóng**. `transferTo` không thay đổi chủ sở hữu chỉ vì nó chuyển dữ liệu.

| Trường hợp | Ai sở hữu? | Sau `transferTo` phải làm gì? |
|---|---|---|
| Caller mở cả input và output rồi gọi helper | Caller | Helper trả về số byte; caller đóng cả hai |
| Helper tự mở cả hai stream trong cùng phương thức | Helper | Dùng `try-with-resources` cho cả input và output |
| Helper mở input từ tệp nhưng nhận output từ caller | Input thuộc helper; output thuộc caller | Helper chỉ đóng input; giữ output mở |
| Helper chuyển byte ra `System.out` | Thường thuộc ứng dụng/môi trường chạy | Không đóng `System.out` trong helper |
| Framework cấp stream cho callback | Theo hợp đồng framework | Làm đúng quy định ownership của API đang dùng |

**Không có quy tắc “ai gọi `transferTo` thì phải đóng cả hai”.** Ngược lại, cũng không có quy tắc “stream nào được truyền vào hàm cũng không bao giờ được đóng”: nếu API nói rõ ownership được chuyển giao, bên nhận có thể có trách nhiệm đóng.

## 3. Ví dụ hoàn chỉnh: `transferTo` không đóng input hoặc output

Ví dụ Java 17+ dưới đây theo dõi xem `close()` đã được gọi chưa. Ta dùng `ByteArrayInputStream` và `ByteArrayOutputStream` để chương trình có thể chạy độc lập, không cần tệp ngoài. Hai lớp `TrackedInput` và `TrackedOutput` là wrapper đánh dấu mỗi lần phương thức `close()` được gọi.

Lưu thành **`TransferToOwnershipDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class TransferToOwnershipDemo {
    static final class TrackedInput extends FilterInputStream {
        boolean closed;

        TrackedInput(InputStream delegate) {
            super(delegate);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    static final class TrackedOutput extends FilterOutputStream {
        boolean closed;

        TrackedOutput(OutputStream delegate) {
            super(delegate);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    static long copyBorrowed(InputStream source, OutputStream destination)
            throws IOException {
        return source.transferTo(destination);
    }

    public static void main(String[] args) throws IOException {
        byte[] original = "Java I/O".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream storage = new ByteArrayOutputStream();
        TrackedInput input = new TrackedInput(new ByteArrayInputStream(original));
        TrackedOutput output = new TrackedOutput(storage);

        try (input; output) {
            long bytesCopied = copyBorrowed(input, output);
            System.out.println("Transferred: " + bytesCopied + " byte");
            System.out.println("After transferTo: inputClosed=" + input.closed
                    + ", outputClosed=" + output.closed);

            output.write('!');
            output.flush();
            System.out.println("After extra write: "
                    + storage.toString(StandardCharsets.UTF_8));
        }

        System.out.println("After try: inputClosed=" + input.closed
                + ", outputClosed=" + output.closed);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 TransferToOwnershipDemo.java
java TransferToOwnershipDemo
~~~

Kết quả chuẩn:

~~~text
Transferred: 8 byte
After transferTo: inputClosed=false, outputClosed=false
After extra write: Java I/O!
After try: inputClosed=true, outputClosed=true
~~~

**Giải thích theo đúng thứ tự:**

1. `"Java I/O"` có 8 byte trong UTF-8 (toàn ký tự ASCII), được lưu ở `input`.
2. `copyBorrowed` gọi `source.transferTo(destination)`; helper **mượn** hai stream, chỉ trả về số byte, không đóng chúng.
3. Ngay sau `transferTo`, hai cờ `closed` vẫn là `false`. Đây là bằng chứng trong ví dụ rằng **chưa gọi `close()`**.
4. `output.write('!')` vẫn ghi thêm được byte sau khi chuyển; kết quả trong `ByteArrayOutputStream` thành `"Java I/O!"`. Input đã tới cuối luồng, nhưng output không bị đóng do `transferTo`.
5. Kết thúc `try (input; output)`, **try-with-resources** gọi `close` theo thứ tự **ngược với khai báo**: output rồi input. Hai cờ sau khối trở thành `true`.

*Lưu ý:* `ByteArrayInputStream`/`ByteArrayOutputStream` không đại diện cho việc giải phóng file descriptor thực; wrapper ở đây chỉ giúp quan sát **lời gọi `close`**. Với tệp, socket hoặc tài nguyên OS, thiếu `close` có thể gây rò rỉ tài nguyên. `try (input; output)` dùng cú pháp tài nguyên đã khai báo bên ngoài được hỗ trợ từ Java 9; các biến ở đây phải là final hoặc *effectively final*.

## 4. Khi phương thức tự mở cả hai stream

Khi mở tài nguyên từ đường dẫn tệp ngay trong phương thức, phương thức đó thường **sở hữu cả hai**. Hãy dùng `try-with-resources` để đóng cả hai ngay cả khi `transferTo` ném `IOException`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileCopyService {
    public static long copyFile(Path source, Path destination)
            throws IOException {
        try (InputStream input = Files.newInputStream(source);
             OutputStream output = Files.newOutputStream(destination)) {
            return input.transferTo(output);
        }
    }
}
~~~

Đây là một **lớp tiện ích có phương thức `copyFile`**, chưa có `main`; nó được gọi từ code ứng dụng khác. Khi tạo thành công cả hai stream, `try-with-resources` quản lý chúng. Nếu mở output thất bại, input đã mở vẫn được đóng. Nếu `transferTo` thất bại, các tài nguyên đã mở cũng được đóng; ngoại lệ đóng thêm có thể được gắn dưới dạng *suppressed exception*.

**Cẩn thận khi ghi file thật:** `Files.newOutputStream(destination)` với tùy chọn mặc định có thể tạo tệp mới hoặc **cắt ngắn nội dung tệp đã tồn tại**. Nếu không muốn ghi đè, chọn tùy chọn mở phù hợp, chẳng hạn `StandardOpenOption.CREATE_NEW` theo hợp đồng tác vụ. Quyền sở hữu stream là vấn đề khác với chính sách thay thế dữ liệu đích.

Không cần gọi `input.close()`/`output.close()` lần nữa bên trong khối `try`. Hạn chế đóng thủ công ở nhiều nhánh vì dễ bỏ sót tài nguyên khi có ngoại lệ.

## 5. Khi helper chỉ nhận stream do caller cung cấp

Trong code thư viện, một hàm sao chép thường không biết liệu input/output còn được dùng tiếp hay không. Hợp đồng mượn stream nên rõ ràng:

~~~java
// Hàm này chỉ dùng hai stream do caller sở hữu.
// Hàm không close và không tự quyết định flush cho output.
static long transfer(InputStream input, OutputStream output)
        throws IOException {
    return input.transferTo(output);
}
~~~

Đây là **đoạn phương thức minh họa** cần đặt vào một lớp có import `java.io.InputStream`, `java.io.OutputStream` và `java.io.IOException`. Caller có thể mở chúng trong `try-with-resources` và gọi helper:

~~~java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(destination)) {
    long count = transfer(input, output);
    System.out.println("Copied: " + count);
}
~~~

Các biến `source`, `destination` là `Path` đã được khai báo; đoạn này minh họa cách sử dụng, không phải một chương trình độc lập.

Một trường hợp **quyền sở hữu hỗn hợp**:

~~~java
// Helper tự mở input: helper phải đóng input.
// destination do caller đưa vào: helper không đóng destination.
static long sendFile(Path path, OutputStream destination)
        throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return input.transferTo(destination);
    }
}
~~~

Nếu gọi `sendFile(path, System.out)`, helper đóng **input tệp** nhưng vẫn để **`System.out` mở** để ứng dụng còn in được các thông báo khác.

Ngược lại, viết như sau là không phù hợp với hợp đồng mượn stream:

~~~java
// SAI nếu caller vẫn sở hữu output:
try (OutputStream borrowed = output) {
    input.transferTo(borrowed);
}
// borrowed.close() đã được gọi, có thể đóng output của caller.
~~~

`try-with-resources` là cơ chế đóng đúng khi code **sở hữu** tài nguyên; đặt stream được mượn vào `try` có thể vô tình chiếm luôn quyền đóng. Cú pháp hợp lệ không có nghĩa hợp đồng ownership là đúng.

## 6. `flush()`, `close()` và `transferTo()` khác nhau thế nào?

| Thao tác | Ý nghĩa chính | Có tự đóng input/output không? |
|---|---|---|
| `input.transferTo(output)` | Chuyển các byte còn lại sang output; trả số byte | **Không** |
| `output.flush()` | Yêu cầu đẩy byte đang được buffer ra đích bên dưới | Không đóng |
| `output.close()` | Kết thúc tài nguyên output, thường flush theo lớp triển khai | **Đóng output**; có thể kéo theo stream nằm dưới |
| `input.close()` | Kết thúc tài nguyên input | **Đóng input**; có thể kéo theo stream nằm dưới |
| `try-with-resources` | Gọi `close()` tự động khi ra khỏi khối, cả khi có lỗi | Đóng **các tài nguyên đã khai báo** |

**`transferTo` không đưa ra bảo đảm rằng output đã được `flush`.** Nếu output có buffer như `BufferedOutputStream`, phần byte còn trong buffer có thể cần `flush()` trước khi bên nhận thấy đủ dữ liệu. Việc `flush` khi nào phải theo giao thức và hợp đồng của người sở hữu output: helper mượn output không nên tùy tiện áp đặt đóng hoặc flush nếu chưa được yêu cầu.

**`flush` không đồng nghĩa dữ liệu đã được ghi bền vững trên thiết bị lưu trữ.** Theo hợp đồng chung của `OutputStream`, flush đến lớp bên dưới có thể chỉ tới hệ điều hành; muốn độ bền dữ liệu trên đĩa có thể cần API và quy trình riêng. Đóng output cũng không chứng minh một bên nhận mạng đã xử lý toàn bộ thông điệp.

**Wrapper có thể kéo theo đóng luồng bên dưới:** `BufferedOutputStream`, `FilterOutputStream` và một số stream nén/giải nén thường bao một stream khác. Gọi `close` trên wrapper có thể đóng luôn stream gốc, trong khi một số định dạng cần `finish()` hoặc quy trình riêng để hoàn tất nội dung. Nếu wrapper bọc `System.out` hoặc stream do framework cấp, phải thiết kế ownership cả ở tầng wrapper để tránh đóng mất tài nguyên chung.

## 7. Ngoại lệ, chuyển một phần và khả năng bị chặn

`transferTo` thuận tiện, nhưng không biến I/O thành thao tác nguyên tử:

- Nếu đọc input hoặc ghi output lỗi, `IOException` có thể xuất hiện **sau khi đã ghi một phần byte**. Không được giả định file đích còn rỗng hay source vẫn đứng ở vị trí cũ.
- Nếu dữ liệu đầu vào liên tục hoặc đầu ra chậm, phương thức có thể **chặn** trong lúc chờ đọc/ghi, thậm chí kéo dài không xác định. Với socket và giao thức mạng cần chính sách timeout, hủy hoặc giới hạn dữ liệu từ lớp sở hữu.
- Nếu muốn giới hạn chỉ chuyển một phần dữ liệu, `transferTo` trực tiếp không nhận tham số “tối đa N byte”. Có thể dùng luồng giới hạn thích hợp hoặc vòng đọc/ghi có kiểm soát.
- Khi xử lý lỗi, bên sở hữu stream nên đóng các tài nguyên và quyết định có xóa file đích ghi dở, thử lại hay báo lỗi. Helper chỉ mượn stream nên ném lỗi lên caller trừ khi hợp đồng có quy định xử lý khác.
- Gọi `transferTo` **lần thứ hai** trên input đã ở EOF sẽ không tự gửi lại dữ liệu; muốn chạy lại cần tạo nguồn mới hoặc một luồng hỗ trợ thay đổi vị trí thích hợp.

Luồng đang bị dùng **đồng thời** bởi nhiều thread có thể tạo kết quả không mong muốn, nhất là khi các thread cùng đọc một input hoặc cùng ghi một output. `transferTo` không tự thiết lập giao thức đồng bộ để bảo vệ các lời gọi khác.

## 8. Phân biệt với các API có tên tương tự

- **`InputStream.transferTo(OutputStream)`**: truyền **byte** từ input đang đọc sang output, trả **số byte**; có từ Java 9.
- **`Reader.transferTo(Writer)`**: truyền **ký tự** từ `Reader` sang `Writer`, trả **số ký tự**; có từ Java 10. Bài này nói về **luồng byte**.
- **`Files.copy(Path, Path, ...)`**: API sao chép theo đường dẫn với các lựa chọn xử lý file; hợp đồng tạo/đóng tài nguyên do `Files` quản lý khác với việc tự chuyền hai stream vào `InputStream.transferTo`.
- **`FileChannel.transferTo(...)`**: API kênh (channel), chữ ký/điều kiện truyền khác; không nên suy diễn semantics hay ownership từ phương thức này sang `InputStream.transferTo`.

Khi review code, cần nhận diện **đúng kiểu đối tượng và chữ ký phương thức** trước khi áp dụng quy tắc.

## 9. Các lỗi thường gặp và cách sửa

| Sai lầm | Vấn đề | Cách sửa |
|---|---|---|
| “`transferTo` đóng input, output hộ tôi.” | API không đóng stream; có thể rò rỉ tài nguyên. | Bên sở hữu dùng `try-with-resources` hoặc quản lý vòng đời rõ ràng. |
| “Helper nhận output thì cứ đưa vào `try`.” | Có thể đóng tài nguyên caller còn cần. | Helper mượn output thì chỉ chuyển dữ liệu; caller chịu trách nhiệm đóng. |
| “Sau khi copy, input tự quay về đầu.” | `transferTo` đọc từ vị trí hiện tại tới EOF. | Nếu cần lần đọc mới, mở stream mới hoặc thiết kế hỗ trợ định vị. |
| “Output đã nhận byte thì chắc chắn file/network hoàn tất.” | Có thể còn buffer và giới hạn bảo đảm của tầng lưu trữ/giao thức. | Xác định khi nào cần `flush`, đóng hoặc xác nhận giao thức. |
| “`transferTo` luôn chạy xong và không sinh bản sao dở.” | I/O có thể lỗi giữa chừng hoặc chờ vô hạn. | Có chiến lược timeout/huỷ, cleanup, xử lý dữ liệu ghi một phần. |
| “Dữ liệu UTF-8 nên `transferTo` sẽ giải mã và mã hóa lại.” | `transferTo` chỉ chuyển byte. | Chỉ dùng Reader/Writer với charset khi thực sự cần xử lý ký tự. |
| “`try-with-resources` chỉ dùng khi thành công.” | Đây là cơ chế dọn tài nguyên cả khi lỗi. | Đặt các stream **do mình sở hữu** vào phần khai báo tài nguyên. |

## 10. Tự kiểm tra

**Câu 1.** `input.transferTo(output)` trả về `120L`. Con số 120 là gì? Nếu thao tác thành công, input ở đâu?

> **Đáp án:** 120 là số **byte được chuyển**. Input ở cuối phần dữ liệu có thể đọc; `transferTo` không tự đóng input hay output.

**Câu 2.** Hàm `saveReport(OutputStream out)` nhận output từ caller, tự tạo một `InputStream` đọc báo cáo. Ai đóng gì?

> **Đáp án:** Hàm tự đóng input do mình tạo. Caller đóng (hoặc quản lý) output mà mình sở hữu theo hợp đồng. `transferTo` không thay đổi trách nhiệm đó.

**Câu 3.** Nếu output bọc một `BufferedOutputStream` và helper gọi `transferTo` nhưng caller chưa thấy đủ nội dung, nên xem xét điều gì?

> **Đáp án:** Kiểm tra chính sách buffer và `flush`/`close`, cũng như thời điểm bên nhận đọc dữ liệu. `transferTo` không bảo đảm flush; việc flush hay close cần phù hợp ownership.

**Câu 4.** Nếu đầu vào đã được đọc hết trước `transferTo`, kết quả là gì?

> **Đáp án:** `0` byte được chuyển, vì không còn byte nào để đọc. Output vẫn không bị đóng bởi `transferTo`.

### Ghi nhớ

**`input.transferTo(output)` = chuyển byte còn lại + trả số byte; không đóng hai stream.** Viết code an toàn bằng cách xác định rõ **ai tạo, ai mượn và ai đóng** mỗi tài nguyên, dùng `try-with-resources` tại tầng sở hữu, và xử lý lỗi I/O có thể xảy ra sau khi đã ghi một phần dữ liệu.

**Tài liệu đối chiếu:** [Java SE 17 `InputStream.transferTo`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#transferTo(java.io.OutputStream)) và [Java SE 17 `OutputStream.flush`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html#flush()).