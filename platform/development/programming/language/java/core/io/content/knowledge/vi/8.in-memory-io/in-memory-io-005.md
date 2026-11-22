# SequenceInputStream: nối nhiều nguồn byte trong Java I/O

## 1. Mục tiêu và phạm vi

`java.io.SequenceInputStream` biểu diễn **một luồng byte đầu vào được tạo bằng cách nối tuần tự nhiều `InputStream`**. Khi đọc đến hết nguồn thứ nhất, nó chuyển sang nguồn kế tiếp; chương trình tiêu thụ bên ngoài chỉ cần làm việc với **một** `InputStream`.

Chủ đề này thuộc nhóm **I/O trong bộ nhớ** của Java Core. Các ví dụ chính sử dụng `ByteArrayInputStream` để thấy rõ cơ chế nối dữ liệu; cùng nguyên lý có thể dùng với file streams và các nguồn byte khác khi quản lý tài nguyên cẩn thận.

Sau bài học, bạn có thể:

- Phân biệt **ghép tuần tự (concatenation)** với xen kẽ, trộn hoặc chạy nhiều luồng song song.
- Dùng hai constructor: `SequenceInputStream(InputStream, InputStream)` và `SequenceInputStream(Enumeration<? extends InputStream>)`.
- Giải thích khi nào `read()` trả EOF, khi nào chuyển nguồn, tác động của nguồn rỗng và cách `close()` xử lý các stream thành phần.
- Nối dữ liệu nhị phân và byte UTF-8 mà không tự chèn dấu phân cách hoặc làm hỏng chuỗi nhiều byte.
- Chọn cách đọc/ghi có bộ nhớ giới hạn cho dữ liệu lớn, không lạm dụng `readAllBytes()` hoặc `ByteArrayOutputStream` khi kích thước nguồn không biết trước.
- Nhận diện các trường hợp không nên dùng `SequenceInputStream` và cách xử lý lỗi I/O, vòng đời tài nguyên, nguồn đồng thời.

**Ý chính:** `SequenceInputStream` là một **InputStream chỉ đọc** có thứ tự, đưa ra cùng dãy byte như thể đặt byte của từng nguồn sát nhau. Nó không nhận biết định dạng file, ký tự, bản ghi, delimiter hoặc giao thức.

## 2. Ghép tuần tự diễn ra thế nào?

Giả sử ba nguồn:

```text
InputStream A: [10, 20]
InputStream B: []          (nguồn rỗng)
InputStream C: [30, 40]

SequenceInputStream:
   A đến EOF  -> đóng A, chuyển sang B
   B đến EOF  -> đóng B, chuyển sang C
   C đến EOF  -> đóng C, hết tất cả nguồn

Kết quả đọc: [10, 20, 30, 40]
```

Việc chuyển nguồn diễn ra khi đọc đến **EOF của nguồn hiện tại**, không phải khi một lần gọi `read(byte[])` đọc được ít byte hơn số đã yêu cầu. Trong Java, `InputStream.read()` trả một giá trị từ 0 đến 255 khi đọc được byte; chỉ `-1` biểu thị đã hết dữ liệu. Với `read(byte[], off, len)`, số trả về là số byte thực nhận (hoặc `-1` khi EOF và độ dài yêu cầu khác 0). Không tự cho rằng một lần `read(byte[])` luôn đầy mảng.

### 2.1. Các đặc tính cần ghi nhớ

| Đặc tính | `SequenceInputStream` |
| --- | --- |
| Loại dữ liệu | **Byte**; mỗi byte giữ nguyên giá trị |
| Thứ tự | Đọc hết nguồn 1 rồi tới nguồn 2, 3, ... |
| Xen kẽ dữ liệu | Không; không có round-robin hay merge theo thời gian |
| Tự chèn separator | Không; không thêm khoảng trắng, newline, header hay metadata |
| Tự mã hóa/giải mã | Không; muốn văn bản thì gắn reader/decoder ở đúng chỗ |
| Tự tìm độ dài tổng | Không; luồng chung chỉ biết EOF khi đã đi hết các nguồn |
| Trạng thái đọc | Tiến về trước; không hỗ trợ quay lại một cách tổng quát |
| Đồng thời | Không đọc các nguồn song song để tăng tốc |
| Đóng nguồn | Quản lý các input stream thành phần khi đã đọc hết hoặc khi đóng stream ghép |
| Tình huống nguồn block | Có thể chờ nguồn hiện tại; không tự timeout |
| Loại API | Kế thừa `InputStream`, dùng được với các API nhận `InputStream` |

Điểm cần hiểu về **dữ liệu rỗng**: nếu một nguồn không có byte nào, nó được bỏ qua khi phát hiện EOF; nguồn kế tiếp vẫn được đọc bình thường. Nếu không còn nguồn nào, `SequenceInputStream.read()` trả `-1`.

### 2.2. Dữ liệu kết hợp có phải một file hợp lệ không?

**Không nhất thiết.** Kết quả của phép nối byte là một dãy byte đúng theo thứ tự, nhưng định dạng có thể không còn hợp lệ nếu từng mảnh là các file độc lập:

- Nối hai file văn bản UTF-8 có thể tạo văn bản đọc được nếu cấu trúc hợp lý, nhưng **không tự tạo newline** giữa hai file.
- Nối các byte *phân mảnh từ cùng một file nhị phân* có thể tái tạo file gốc chính xác.
- Nối hai file ZIP, PNG, PDF hoặc dữ liệu nén độc lập không tự tạo một “file hợp nhất” đúng định dạng; điều này phụ thuộc cấu trúc định dạng và yêu cầu của chương trình đọc.
- Với giao thức có header, checksum, độ dài, frame hoặc boundary, chỉ nối byte có thể làm mất ranh giới; cần quy tắc đóng gói/giải mã riêng.

## 3. Hai constructor và quyền sở hữu nguồn

### 3.1. Nối đúng hai `InputStream`

```java
InputStream joined = new SequenceInputStream(first, second);
```

Ở đây `first` và `second` là hai `InputStream` đã được tạo. Khi đọc, thứ tự luôn là **first rồi second**. Hai stream thành phần có thể là `ByteArrayInputStream`, `FileInputStream`, stream từ `Files.newInputStream(...)` hoặc nguồn byte khác.

Một cách dùng quen thuộc:

```java
try (InputStream joined =
        new SequenceInputStream(first, second)) {
    // Đọc từ joined cho đến EOF.
}
```

**Đây là đoạn minh họa:** `first` và `second` cần được tạo trước đó, và trách nhiệm xử lý lỗi khi tạo các nguồn phải được xác định tại nơi mở nguồn.

`SequenceInputStream` sở hữu các nguồn mà nó nhận theo hợp đồng đóng stream: khi một nguồn cạn, nó đóng nguồn vừa đọc xong rồi chuyển sang nguồn tiếp theo; gọi `close()` trên stream ghép sẽ đóng nguồn hiện tại và những nguồn còn lại trong chuỗi. Vì vậy, khi đã chuyển quyền quản lý vào stream ghép, nên coi stream ghép là tài nguyên phải được đóng. Tránh dùng lại nguồn cũ sau khi đã giao cho nó.

### 3.2. Nối nhiều nguồn bằng `Enumeration`

Constructor thứ hai:

```java
SequenceInputStream joined =
        new SequenceInputStream(enumerationOfInputStreams);
```

`enumerationOfInputStreams` có kiểu `Enumeration<? extends InputStream>`. Mỗi nguồn được đưa vào theo thứ tự `Enumeration.nextElement()` trả về. Nếu có 3, 10 hay 100 nguồn, chương trình tiêu thụ bên ngoài vẫn dùng một InputStream.

Java có thể chuyển `List` sang `Enumeration` bằng `Collections.enumeration(list)`:

```java
// Minh họa; first, second, third là các InputStream đã được tạo.
java.util.List<java.io.InputStream> sources =
        java.util.List.of(first, second, third);
java.util.Enumeration<java.io.InputStream> inputs =
        java.util.Collections.enumeration(sources);

try (java.io.SequenceInputStream joined =
        new java.io.SequenceInputStream(inputs)) {
    // Đọc toàn bộ các nguồn theo đúng thứ tự danh sách.
}
```

Các mảnh được nối **theo thứ tự cung cấp**; nếu thứ tự có ý nghĩa, phải xác lập thứ tự ở đầu vào. Đừng tùy tiện duyệt một collection không cam kết thứ tự rồi mặc nhiên cho rằng thứ tự là chính xác.

**Quan trọng với nhiều tệp:** nếu tự mở hàng nghìn stream trước khi tạo `Enumeration`, bạn có thể giữ hàng nghìn file descriptor cùng lúc và phải xử lý lỗi xảy ra ở giữa giai đoạn khởi tạo. `SequenceInputStream` chỉ giúp đọc tuần tự; nó không tự giải quyết việc mở hàng loạt tệp hiệu quả. Xem cách thay thế ở mục 8.

## 4. Ví dụ Java 17+: nối hai mảnh byte chứa UTF-8 nhiều byte

Đây là tình huống quan trọng: chuỗi Unicode `A😀B` được mã hóa thành UTF-8 có **6 byte** (1 byte cho `A`, 4 byte cho emoji và 1 byte cho `B`). Ta cố tình cắt byte ở **giữa** emoji rồi nối lại bằng `SequenceInputStream`. Cách đúng là nối byte trước, sau đó mới giải mã văn bản.

Lưu chương trình sau vào **`SequenceInputStreamDemo.java`** với mã nguồn UTF-8:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.SequenceInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class SequenceInputStreamDemo {
    public static void main(String[] args) throws IOException {
        byte[] original = "A😀B".getBytes(StandardCharsets.UTF_8);

        // Vị trí 3 nằm giữa dãy byte mã hóa emoji.
        byte[] part1 = Arrays.copyOfRange(original, 0, 3);
        byte[] part2 = Arrays.copyOfRange(
                original, 3, original.length);

        try (InputStream joined = new SequenceInputStream(
                new ByteArrayInputStream(part1),
                new ByteArrayInputStream(part2))) {

            byte[] result = joined.readAllBytes();
            System.out.println("Bytes: " + result.length);
            System.out.println("Match: " + Arrays.equals(original, result));
            System.out.println("Text: "
                    + new String(result, StandardCharsets.UTF_8));
        }
    }
}
```

Lệnh biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 SequenceInputStreamDemo.java
java SequenceInputStreamDemo
```

**Stdout chính xác:**

```text
Bytes: 6
Match: true
Text: A😀B
```

**Giải thích:**

1. `getBytes(StandardCharsets.UTF_8)` sinh 6 byte. `part1` nhận ba byte đầu, `part2` nhận ba byte cuối.
2. `ByteArrayInputStream` đọc trực tiếp từ byte array có sẵn trong bộ nhớ; hai phần này là nguồn byte riêng.
3. `SequenceInputStream` trả byte của `part1` rồi nối tiếp byte của `part2`, không bỏ byte nào và không chèn ký tự giữa chúng.
4. `Arrays.equals` trả `true` vì thứ tự byte khôi phục đúng nguyên bản.
5. Chỉ khi dữ liệu đã được nối, `new String(result, UTF_8)` mới giải mã dãy UTF-8 hoàn chỉnh thành `A😀B`.

Nếu thay vào đó giải mã từng mảnh UTF-8 riêng lẻ rồi nối hai `String`, việc cắt giữa một chuỗi byte của code point có thể gây replacement character hoặc lỗi giải mã tùy decoder. Với dữ liệu văn bản bị phân mảnh theo byte, **hãy decode trên luồng byte ghép** hoặc sau khi đã khôi phục dãy byte đúng.

**Giới hạn ví dụ:** `readAllBytes()` giữ toàn bộ kết quả trong RAM, phù hợp với ví dụ rất nhỏ này. Đối với các nguồn lớn, dùng đọc theo khối hoặc `transferTo` đến đích không tích lũy toàn bộ nội dung.

## 5. Ví dụ Java 17+: nối nhiều nguồn và truyền byte không cần vòng lặp

Ví dụ này dùng `Enumeration` của ba nguồn byte; nguồn giữa rỗng để kiểm tra chuyển nguồn và tránh tự chèn delimiter. Đích là `ByteArrayOutputStream` nhằm quan sát kết quả ngay tại bộ nhớ.

Lưu vào **`MultiSourceSequenceDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.SequenceInputStream;
import java.io.IOException;
import java.util.Arrays;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;

public class MultiSourceSequenceDemo {
    public static void main(String[] args) throws IOException {
        List<InputStream> parts = List.of(
                new ByteArrayInputStream(new byte[] {1, 2}),
                new ByteArrayInputStream(new byte[0]),
                new ByteArrayInputStream(new byte[] {3, 4, 5})
        );
        Enumeration<InputStream> sources =
                Collections.enumeration(parts);

        try (InputStream joined = new SequenceInputStream(sources);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            long transferred = joined.transferTo(output);

            System.out.println("Transferred: " + transferred);
            System.out.println("Result: "
                    + Arrays.toString(output.toByteArray()));
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MultiSourceSequenceDemo.java
java MultiSourceSequenceDemo
```

**Stdout:**

```text
Transferred: 5
Result: [1, 2, 3, 4, 5]
```

Ở đây `transferTo` (có từ Java 9 trên `InputStream`) chuyển byte đến `OutputStream` và trả về **tổng số byte đã truyền**. Nguồn rỗng không tạo giá trị và không làm ngừng việc đọc các nguồn sau. Kết quả được in bằng `Arrays.toString` nên bạn có thể kiểm tra cả thứ tự và số phần tử.

**Điều cần phân biệt:** `ByteArrayOutputStream` tích lũy toàn bộ byte trong RAM, có thể dùng trong bài học và dữ liệu nhỏ đã giới hạn. Nếu nguồn lớn hoặc đến từ mạng, thay đích bằng file stream, socket stream hoặc đầu ra có khả năng xử lý tuần tự và áp dụng quota khi cần. `transferTo` không tự giới hạn số byte của nguồn.

## 6. Quản lý EOF, `close()` và exception

### 6.1. Khi nào một nguồn được đóng?

`SequenceInputStream` đọc hết một nguồn thì chuyển sang nguồn khác, đồng thời đóng nguồn đã cạn. Khi đóng stream ghép, các stream được quản lý còn lại cũng được đóng theo hợp đồng lớp. Điều này khác với việc tự tạo và giữ một danh sách `InputStream` độc lập rồi quên đóng từng stream.

Cần lưu ý hai nhóm tình huống:

- **Đọc đến hết:** qua từng EOF, các nguồn đã dùng được đóng và nguồn tiếp theo được chọn. Khi không còn nguồn, stream ghép trả EOF.
- **Dừng sớm/ngoại lệ:** việc bỏ dở giữa chừng mà **không đóng** stream ghép có thể để lại file handle/network stream. Bọc stream ghép trong `try-with-resources`, kể cả khi định đọc một phần dữ liệu.

Các `ByteArrayInputStream` trong ví dụ giữ byte trong bộ nhớ và thao tác `close()` của chúng không có tác dụng giải phóng file handle. Với `FileInputStream` hoặc stream mạng, việc đóng đúng tài nguyên đặc biệt quan trọng.

### 6.2. Trách nhiệm khi tạo nguồn bị lỗi giữa chừng

Giả sử muốn nối hai file bằng:

```java
// Minh họa ý tưởng, có nguy cơ rò nguồn nếu mở file thứ hai thất bại.
InputStream first = Files.newInputStream(path1);
InputStream second = Files.newInputStream(path2);
InputStream joined = new SequenceInputStream(first, second);
```

Đây **không phải một mẫu hoàn chỉnh an toàn**: nếu việc mở `path2` ném `IOException`, `first` đã mở nhưng chưa được giao cho stream ghép; mã cần cơ chế đóng `first` khi bước thứ hai thất bại. Với tệp thật, nên dùng `try-with-resources` theo từng nguồn ngay lúc mở, hoặc hàm khởi tạo có cleanup khi lỗi; xác định rõ trách nhiệm đóng để tránh bỏ quên nguồn.

Một cách **đơn giản, chắc chắn** khi chỉ cần ghép nhiều file (không bắt buộc phải có một InputStream chung) là xử lý từng file trong một vòng lặp và đóng từng nguồn ngay sau khi chuyển xong, xem mục 8. Với số lượng nguồn lớn, cách đó còn tránh mở quá nhiều file đồng thời.

### 6.3. Hành vi khi một nguồn đọc bị lỗi

Nếu `read()` của một stream thành phần ném `IOException`, phép đọc từ `SequenceInputStream` có thể thất bại. Không mặc định nó sẽ “bỏ qua nguồn lỗi” như nguồn rỗng rồi tự tiếp tục ở nguồn kế tiếp. Với dữ liệu yêu cầu tính toàn vẹn, phải xử lý lỗi như một kết quả thất bại: tránh công bố file ghép thiếu phần hoặc tự nhận là thành công.

Nếu writer đích ném lỗi khi dùng `transferTo`, đích cũng có thể đã có **một phần byte**. `SequenceInputStream` không cung cấp transaction, rollback, checksum hay atomic replacement. Khi cần bảo vệ file đích, dùng tệp tạm, xác minh số byte/checksum/định dạng, rồi áp dụng chính sách công bố thích hợp.

### 6.4. Không dựa vào `available()` để biết tổng số byte

`InputStream.available()` nói về ước lượng số byte có thể đọc không phải chờ từ stream tại thời điểm đó; nó **không phải phép đo tổng dung lượng của tất cả nguồn** và không phải tín hiệu EOF. Giá trị 0 không chứng minh đã hết input. Với `SequenceInputStream`, chỉ nên dừng vòng đọc khi `read()`/`read(byte[])` báo EOF theo hợp đồng.

## 7. Đọc streaming và giới hạn bộ nhớ

`SequenceInputStream` chỉ cung cấp một góc nhìn nối các stream. Nó không bắt buộc ứng dụng phải giữ tất cả byte. Tuy nhiên, bộ nhớ dùng bao nhiêu còn phụ thuộc **nguồn** và **đích**:

| Pipeline | Đặc điểm bộ nhớ |
| --- | --- |
| Hai `ByteArrayInputStream` trên `byte[]` đã tồn tại | Byte đã nằm trong RAM trước khi ghép; `SequenceInputStream` không tự ghép thành một mảng lớn |
| `SequenceInputStream` → `readAllBytes()` | Tạo kết quả trong RAM theo toàn bộ dữ liệu đọc; không phù hợp với input không giới hạn |
| `SequenceInputStream` → `ByteArrayOutputStream` | Đầu ra tích lũy toàn bộ dữ liệu trong RAM |
| `SequenceInputStream` → `Files.newOutputStream(...)` qua `transferTo` | Có thể truyền từng khối, không cần giữ mọi byte trong RAM |
| Nhiều file mở từ trước trong một `List<InputStream>` | Có thể giữ nhiều file descriptor; độ lớn của từng file không quyết định số descriptor |
| Nhiều stream từ mạng | Có thể block khi đọc, cần quota/timeouts/cancellation của giao thức bên ngoài |

### 7.1. Khi nào dùng `transferTo`?

Với Java 17+, nếu chỉ cần **chuyển hết byte** đến một `OutputStream`, có thể dùng:

```java
// Minh họa, input đã là một SequenceInputStream đang mở;
// output là OutputStream đang mở.
long copied = input.transferTo(output);
```

Phương thức này chuyển byte theo từng khối và trả tổng byte đã gửi, song vẫn đọc **đến EOF**, không tự áp dụng quota, thời gian chờ hay chính sách đích. Nếu bài toán có giới hạn kích thước, phải tự đo trước/trong khi chuyển theo cách không vượt quá ngưỡng; kiểm tra `copied` sau khi chuyển không ngăn việc đích đã nhận quá nhiều byte.

### 7.2. Đọc theo khối khi phải xử lý dữ liệu

Nếu muốn tính checksum hoặc xử lý chunk có kiểm soát, đọc từng khối là lựa chọn rõ ràng:

```java
// Minh họa: input và output phải được quản lý bằng try-with-resources.
byte[] buffer = new byte[16 * 1024];
int count;
while ((count = input.read(buffer)) != -1) {
    if (count > 0) {
        output.write(buffer, 0, count);
    }
}
```

Giá trị `count` có thể nhỏ hơn kích thước mảng, đặc biệt khi gần cuối một nguồn hoặc cuối chuỗi. Phải truyền **đúng `count` byte** sang đích, không luôn ghi `buffer.length` (vì phần còn lại có thể chứa byte cũ từ lượt trước).

**Đừng coi một lần đọc ngắn là hết một stream thành phần.** `SequenceInputStream` chịu trách nhiệm tìm EOF thật và chuyển nguồn. Ở vòng xử lý bên ngoài, điều kiện kết thúc là `-1`.

### 7.3. Giới hạn nguồn lớn hoặc không đáng tin

Nếu các nguồn đến từ file do người dùng tải lên, mạng hoặc kho lưu trữ không kiểm soát, hãy đặt:

- **Quota tổng số byte** sau khi nối và, nếu cần, quota từng nguồn.
- **Timeout/deadline/cancellation** cho nguồn có thể chờ hoặc không phát EOF.
- **Giới hạn số nguồn** trong Enumeration/List để tránh quá nhiều handle.
- **Kiểm tra thứ tự và danh tính phần** (chẳng hạn chunk index, version, size, checksum); `SequenceInputStream` chỉ tôn trọng thứ tự được giao, không xác minh các mảnh đúng.
- **Xử lý khi một phần thiếu hoặc bị lỗi:** không công bố kết quả nối như file hoàn chỉnh.
- **Quản lý đầu ra tạm:** nếu ghi file quan trọng, lưu tạm và xác minh toàn vẹn trước khi thay thế kết quả cũ.

## 8. Những lựa chọn thay thế

`SequenceInputStream` phù hợp khi **một API cần đúng một `InputStream`** đại diện cho nhiều nguồn tuần tự. Không phải bài toán nối dữ liệu nào cũng cần đến lớp này.

### 8.1. Nối nhiều file với số lượng lớn

Nếu mục tiêu là ghép nhiều tệp lần lượt vào một tệp đích, vòng lặp mở **một file tại một thời điểm** thường dễ kiểm soát file handle hơn. Đoạn minh họa dưới đây có biến `paths` là một `List<Path>` hợp lệ và `outputPath` là `Path` đích; mã gọi phải kiểm tra không đưa file đích vào danh sách nguồn:

```java
// Đoạn minh họa (paths và outputPath cần được cung cấp).
try (java.io.OutputStream target =
        java.nio.file.Files.newOutputStream(outputPath)) {
    for (java.nio.file.Path path : paths) {
        try (java.io.InputStream source =
                java.nio.file.Files.newInputStream(path)) {
            source.transferTo(target);
        }
    }
}
```

Ưu điểm: chỉ mở một stream nguồn mỗi lượt, đóng ngay sau khi xong; xử lý lỗi được gắn với tên từng file dễ dàng. Nhược điểm: nếu nơi tiêu thụ yêu cầu **một InputStream** thay vì OutputStream đích do ta kiểm soát, `SequenceInputStream` thuận tiện hơn.

Chú ý: đây vẫn là phép **nối byte**, không tự tạo một ZIP/PDF/PNG hợp lệ từ các file độc lập. Nếu đích đã tồn tại, `Files.newOutputStream(outputPath)` thông thường ghi đè nội dung theo các tùy chọn mở mặc định; cân nhắc tệp tạm nếu cần bảo toàn bản cũ khi phát sinh lỗi.

### 8.2. Ghép dữ liệu đã nằm trong bộ nhớ

Nếu tổng dữ liệu **nhỏ và có giới hạn**, có thể dùng `ByteArrayOutputStream` cùng `write(byte[])` để tạo mảng kết quả:

```java
// Minh họa với các mảng byte nhỏ có sẵn.
java.io.ByteArrayOutputStream output =
        new java.io.ByteArrayOutputStream();
output.writeBytes(firstBytes);
output.writeBytes(secondBytes);
byte[] joined = output.toByteArray();
```

`writeBytes` có từ Java 11. Với cách này, kết quả được **materialize** thành một `byte[]` mới; dễ lưu trữ/sử dụng lại nhưng tốn bộ nhớ theo tổng số byte. `SequenceInputStream` cung cấp **góc nhìn stream**, thích hợp khi muốn tiêu thụ từng phần mà không xây một mảng ghép trung gian.

### 8.3. Đọc dữ liệu văn bản

Nếu các nguồn là **văn bản đã được mã hóa đúng cùng charset** nhưng bị chia tùy ý theo byte, có thể nối byte bằng `SequenceInputStream` rồi tạo **một** `InputStreamReader` phía ngoài:

```java
// Minh họa; first và second là InputStream nguồn,
// truyền quyền đóng nguồn vào SequenceInputStream.
try (java.io.Reader reader = new java.io.InputStreamReader(
        new java.io.SequenceInputStream(first, second),
        java.nio.charset.StandardCharsets.UTF_8)) {
    char[] characters = new char[1024];
    while (reader.read(characters) != -1) {
        // Xử lý từng khối ký tự (sử dụng số char thực đọc
        // nếu cần chuyển tiếp hoặc lưu trữ dữ liệu).
    }
}
```

Điểm mấu chốt là **decoder duy nhất nằm ngoài luồng byte ghép**, vì một code point UTF-8 có thể có byte ở hai nguồn khác nhau. Để mã đầy đủ, phải tạo `first`/`second` và xử lý lỗi khởi tạo như mục 6. Không chọn cách trên nếu các nguồn thực chất chứa dữ liệu với các charset khác nhau; phải decode từng nguồn theo charset riêng và xác định quy tắc ghép ở mức ký tự.

### 8.4. Khi cần xen kẽ hoặc ghép có cấu trúc

Nếu muốn nhận lần lượt một byte từ nguồn A rồi một byte từ B (round-robin), `SequenceInputStream` không làm điều đó. Nếu muốn merge theo timestamp hoặc khóa sắp xếp, phải dùng thuật toán merge theo dữ liệu. Nếu muốn gắn header, length-prefix, delimiter, checksum hay nén nhiều file thành archive, hãy dùng writer/parser theo định dạng được yêu cầu.

## 9. Các bẫy kỹ thuật quan trọng

1. **Nhầm nối tuần tự với đọc song song:** `SequenceInputStream` xử lý hết nguồn trước rồi mới đến nguồn sau; không tự cải thiện băng thông bằng nhiều thread.
2. **Dùng `readAllBytes()` với nguồn lớn:** tạo mảng kết quả tăng theo dữ liệu; có thể hết heap.
3. **Tin rằng nối hai file độc lập sẽ tạo một file hợp lệ:** định dạng có header/footer, frame hoặc index cần xử lý riêng.
4. **Quên dấu phân cách:** `"hello"` + `"world"` trở thành `"helloworld"`; phải chủ động thêm newline nếu đó là yêu cầu.
5. **Giải mã UTF-8 từng chunk trước khi nối:** có thể cắt giữa byte mã hóa của một code point và làm hỏng văn bản.
6. **Không đóng stream ghép:** các nguồn chưa đọc hết vẫn có thể giữ tài nguyên.
7. **Mở trước quá nhiều file:** dù đọc tuần tự, các nguồn được tạo sớm có thể cùng chiếm file descriptor.
8. **Không xử lý lỗi khi khởi tạo nguồn:** file thứ hai không mở được có thể làm rò file thứ nhất đã mở.
9. **Ghi thiếu/thừa byte do không dùng kết quả `read(byte[])`:** luôn dùng số byte thực nhận.
10. **Dùng `available() == 0` để dừng:** đây không phải EOF, đặc biệt với stream mạng.
11. **Không ràng buộc thứ tự phần:** ghép chunk sai thứ tự tạo nội dung sai dù không có lỗi I/O.
12. **Không xử lý kết quả ghi dở:** nếu đầu ra lỗi, dữ liệu đích có thể đã chứa một phần.
13. **Coi `SequenceInputStream` là stream có thể seek/reset:** đây là luồng tuần tự, không hỗ trợ truy cập ngẫu nhiên như file channel.
14. **Cho rằng ByteArrayInputStream phải giải phóng tài nguyên ngoài heap:** nguồn mảng byte không giữ file descriptor; việc close có hiệu ứng khác với file/socket.
15. **Gọi API chuyển toàn bộ trên nguồn không bao giờ EOF:** có thể block lâu; cần timeout và giới hạn thuộc tầng nguồn/giao thức.

## 10. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Đúng thứ tự và nguồn rỗng

Nối ba `ByteArrayInputStream` chứa `{5, 6}`, `{}`, `{7}`. Dùng `read()` đến `-1`, in từng byte; kết quả phải theo thứ tự `5`, `6`, `7`. Giải thích vì sao nguồn rỗng không làm toàn bộ chuỗi dừng.

### Bài tập 2 — Nhiều mảnh từ một dữ liệu gốc

Lấy `byte[]` từ chuỗi `"Tiếng Việt 😀"` mã hóa UTF-8, chia thành ba mảnh tại **bất kỳ vị trí byte nào**, dùng `SequenceInputStream` ghép lại. So sánh mảng byte với mảng gốc, rồi giải mã một lần sau khi nối. Nếu chia ngay giữa emoji, vì sao vẫn khôi phục văn bản đúng?

### Bài tập 3 — So sánh bộ nhớ

Dùng tổng nguồn có kích thước đã giới hạn để so sánh:
- `SequenceInputStream` → `readAllBytes()`;
- `SequenceInputStream` → `ByteArrayOutputStream`;
- `SequenceInputStream` → `Files.newOutputStream(...)` thông qua `transferTo`.

Nêu điểm nào giữ kết quả trong heap; điểm nào có thể chuyển từng khối. Không thử với nguồn không giới hạn hoặc file rất lớn nếu chưa có quota tài nguyên.

### Bài tập 4 — Phát hiện lỗi ghép

Mô phỏng ba nguồn, trong đó nguồn thứ hai ném `IOException` giữa chừng. Kiểm tra ngoại lệ được truyền ra, stream ghép được đóng qua `try-with-resources` và kết quả tạm được loại bỏ. Tại sao không được báo thành công chỉ vì đã sao chép được byte của nguồn thứ nhất?

### Bài tập 5 — Lựa chọn API

Giải thích công cụ phù hợp cho từng trường hợp:

- API chỉ nhận một `InputStream` nhưng dữ liệu được chia thành nhiều nguồn byte theo thứ tự.
- Có 10.000 tệp cần ghép vào một tệp đích; không nên mở đồng thời 10.000 file descriptor.
- Có 2 file ZIP độc lập muốn tạo một archive đúng định dạng.
- Cần xen kẽ các frame từ hai nguồn theo timestamp.
- Muốn ghép một vài mảng byte nhỏ thành `byte[]` để xử lý lại.

**Đáp án định hướng:** `SequenceInputStream`; vòng lặp mở/đóng từng nguồn; thư viện/archive writer chuẩn; thuật toán merge theo timestamp; `ByteArrayOutputStream` hoặc sao chép mảng.

## 11. Tóm tắt kiến thức cốt lõi

- `SequenceInputStream` cung cấp **một luồng InputStream** đại diện cho nhiều nguồn byte **nối theo thứ tự**.
- Hai constructor nhận **hai stream** hoặc **Enumeration các stream**; EOF từng nguồn kích hoạt việc chuyển sang nguồn kế, còn EOF cuối cùng kết thúc toàn chuỗi.
- Nó không chèn delimiter, không tạo định dạng ghép, không chạy song song và không xử lý byte theo Unicode/charset.
- Khi ghép byte văn bản bị cắt giữa ký tự đa byte, **nối byte trước, decode sau** bằng đúng charset.
- `try-with-resources` bảo đảm đóng stream ghép; với tài nguyên thực, cần quản lý cả lỗi khởi tạo trước khi trao quyền sở hữu.
- Với nguồn lớn, truyền theo khối đến đích không tích lũy dữ liệu; tránh `readAllBytes()` và `ByteArrayOutputStream` nếu toàn bộ kết quả có thể vượt bộ nhớ.
- Nếu chỉ cần ghi nhiều file theo thứ tự vào một file, vòng lặp mở và đóng **từng file** có thể đơn giản và tiết kiệm file descriptor hơn.

Một lựa chọn tốt là lựa chọn giải quyết đúng nhu cầu **nối byte tuần tự**, **vòng đời tài nguyên**, **bộ nhớ** và **tính đúng của định dạng**, thay vì dùng `SequenceInputStream` cho mọi hình thức “ghép dữ liệu”.