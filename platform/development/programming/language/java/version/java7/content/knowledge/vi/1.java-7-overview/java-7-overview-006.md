# Java 7 — Lựa chọn tính năng theo bài toán và kiểm chứng bằng chương trình nhỏ

## Mục tiêu

Khi gặp một yêu cầu, đừng bắt đầu bằng câu hỏi “Java 7 có những tính năng nào?”. Hãy xác định **vấn đề cần giải quyết**, **điều kiện đúng/sai có thể quan sát** và **cái giá của từng lựa chọn**, rồi chọn đúng tính năng cần thiết. Bài này tập trung vào những khả năng xuất hiện từ Java 7 **vẫn hữu ích trên JDK hiện đại**: `try-with-resources`, NIO.2 (`Path`/`Files`), multi-catch, diamond operator (`<>`), `switch` với `String` và một số tiện ích biểu đạt dữ liệu, xử lý tác vụ CPU.

Các chương trình bên dưới chạy với **JDK 17 trở lên**; chúng dùng các cấu trúc và API Java 7 vẫn được hỗ trợ. Không cần cài hoặc vận hành một JDK cũ để học nội dung này.

Sau bài học, bạn có thể:
- Đổi một yêu cầu mơ hồ thành các tiêu chí chọn tính năng: tính đúng, xử lý lỗi, quản lý tài nguyên, khả năng đọc hiểu và chi phí.
- Viết một chương trình nhỏ có input rõ ràng và output dự kiến để kiểm chứng giả thuyết.
- Giải thích vì sao chọn một tính năng, khi nào nên tránh nó và cách nhận biết chương trình chỉ “chạy được” nhưng chưa đáp ứng yêu cầu.

## 1. Chọn theo bài toán, không chọn theo tên tính năng

| Nhu cầu thực tế | Tính năng phù hợp | Lợi ích cần kiểm chứng | Khi nào cần cân nhắc khác |
| --- | --- | --- | --- |
| Đọc tệp, kết nối hoặc luồng có vòng đời cần đóng | `try-with-resources` với đối tượng `AutoCloseable` | `close()` được gọi khi rời khối, kể cả lúc phát sinh lỗi | Đừng bọc đối tượng không giữ tài nguyên chỉ để dùng cú pháp mới |
| Đọc, ghi, tạo, di chuyển hay xử lý đường dẫn trên hệ tệp | NIO.2: `Path`, `Files` | Thao tác rõ đường dẫn, charset, lỗi I/O; chạy được với tệp tạm | Không suy ra thao tác chắc chắn thành công chỉ từ `Files.exists` |
| Hai kiểu exception thật sự có cùng cách khôi phục | Multi-catch: `catch (A | B e)` | Một nhánh xử lý chung, không lặp code | Nếu cần thông báo/hành động khác nhau thì viết các nhánh `catch` riêng |
| Khai báo cấu trúc generic lồng nhau | Diamond: `new HashMap<>()` | Giảm lặp kiểu mà vẫn được trình biên dịch kiểm tra | Không dùng raw type hay nghĩ rằng generic được kiểm tra đầy đủ lúc runtime |
| Phân nhánh theo một tập chuỗi xác định | `switch` với `String` | Thể hiện các lựa chọn hữu hạn, mỗi nhánh có hành vi rõ | Chú ý `null`, chữ hoa/thường; trên JDK mới cũng có cú pháp switch hiện đại hơn |
| Biểu diễn cờ bit hoặc số dài dễ đọc | Số nhị phân `0b...` và dấu gạch dưới giữa các chữ số | Giá trị không đổi nhưng literal dễ kiểm tra bằng mắt | Không thêm ký hiệu khi nó làm ý nghĩa số kém rõ ràng |
| Bài toán tính toán CPU có thể chia nhỏ độc lập | `ForkJoinPool` | Có khả năng tận dụng nhiều lõi sau khi đo | Không giả định sẽ nhanh hơn; không mặc định dùng cho I/O chặn hoặc việc quá nhỏ |

Ví dụ: “Đọc file UTF-8 và đếm số dòng” dẫn thẳng tới `Path`/`Files` và `try-with-resources`. Diamond hay multi-catch chỉ được thêm nếu **bài toán cụ thể** tạo nhu cầu cho chúng. Việc dùng được một cú pháp không chứng minh rằng nó cần thiết.

### Năm câu hỏi trước khi viết code

1. **Đầu vào và kết quả nào là đúng?** Ví dụ: tệp chứa `alpha\nbeta\n` thì phải có 2 dòng.
2. **Tài nguyên nào phải được giải phóng?** Luồng đọc file phải đóng cả khi đọc lỗi; tệp tạm cần dọn.
3. **Lỗi nào có ý nghĩa khác nhau?** Không có file, file không đọc được và dữ liệu sai định dạng đôi khi cần thông báo riêng.
4. **Có cần đo hiệu năng không?** Chỉ tối ưu sau khi xác định quy mô đầu vào và đo đúng nút thắt.
5. **Có phương án đơn giản hơn không?** Dùng API tiêu chuẩn và cú pháp nhỏ nhất đáp ứng tiêu chí trước khi thêm trừu tượng hóa.

## 2. Quy trình kiểm chứng bằng một chương trình nhỏ

Đối với mỗi lựa chọn, thực hiện chu trình sau:

1. **Viết giả thuyết** dưới dạng có thể sai: “Nếu dùng `try-with-resources`, luồng đọc sẽ được đóng trước khi xóa tệp.”
2. **Chọn ca bình thường, ca lỗi và ranh giới**: file có 2 dòng, file trống, file không tồn tại; cấu hình hợp lệ, sai số, vượt ngưỡng.
3. **Giữ thí nghiệm nhỏ**: một file `.java`, một `main`, dữ liệu tạm do chương trình tạo; không cần database, web service hay thư viện ngoài.
4. **Ghi trước output kỳ vọng**: phân biệt dữ liệu in ra với lỗi biên dịch, exception và thời gian chạy.
5. **Biên dịch, chạy, đổi đúng một giả định**, đối chiếu kết quả và lý giải khác biệt.
6. **Kết luận có điều kiện**: tính năng giải quyết vấn đề nào, có giới hạn nào; không suy rộng từ một ca nhỏ thành cam kết cho production.

Lệnh chạy cho từng thí nghiệm (ở thư mục chứa file, có `javac` và `java` trong `PATH`):

```bash
javac -encoding UTF-8 FileProbe.java
java FileProbe
```

Thay `FileProbe` bằng tên lớp của thí nghiệm tương ứng. Tên file phải khớp tên `public class`; chạy trên JDK 17+.

## 3. Thí nghiệm A — NIO.2 + try-with-resources cho file UTF-8

**Bài toán:** Đọc tệp văn bản, đếm số dòng, không giữ luồng đọc mở và không để lại tệp tạm sau thí nghiệm.

**Lựa chọn:** `Files.createTempFile`, `Files.write`, `Files.newBufferedReader` và `try-with-resources`. `Path` đại diện cho đường dẫn; `Files` thực hiện thao tác. Charset được chỉ định rõ để không phụ thuộc encoding mặc định của máy.

Lưu thành `FileProbe.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class FileProbe {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("java7-probe-", ".txt");
        try {
            Files.write(file, "alpha\nbeta\n".getBytes(StandardCharsets.UTF_8));
            int lines = 0;
            try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                while (reader.readLine() != null) {
                    lines++;
                }
            }
            System.out.println("lines=" + lines);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FileProbe.java
java FileProbe
```

Kết quả:

```text
lines=2
```

**Điều đã kiểm chứng:** `Files` đọc/ghi trên `Path`; `BufferedReader` được đóng khi ra khỏi `try`; sau đó `finally` dọn tệp tạm. Khi thêm một dòng vào chuỗi dữ liệu, kết quả mong đợi là `lines=3`. Nếu thay dữ liệu bằng chuỗi rỗng, kết quả là `lines=0`.

**Giới hạn:** `try-with-resources` chỉ tự đóng tài nguyên khai báo trong phần khai báo của `try`; nó không tự xóa tệp đã tạo. Thao tác I/O có thể thất bại vì quyền, dung lượng, đường dẫn hoặc thiết bị. Luôn xử lý `IOException` phù hợp với hợp đồng của ứng dụng. Với file rất lớn, đọc tuần tự như ví dụ hữu ích hơn nạp toàn bộ file chỉ để đếm dòng.

## 4. Thí nghiệm B — Multi-catch khi chính sách xử lý thật sự giống nhau

**Bài toán:** Một công cụ kiểm tra nhanh xem file cấu hình có chứa một số cổng trong khoảng `1..65535` hay không. Hợp đồng *riêng của công cụ này* quy định: file mất hoặc giá trị sai đều cho kết quả `false`.

**Lựa chọn:** Đọc dữ liệu với NIO.2 và gom `IOException` (đọc thất bại) cùng `NumberFormatException` (không phân tích được số) vào **một** multi-catch, bởi cả hai cùng có hành động là trả `false`.

Lưu thành `ErrorPolicyProbe.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ErrorPolicyProbe {
    private static boolean validPort(Path file) {
        try (BufferedReader reader =
                 Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            int port = Integer.parseInt(reader.readLine());
            return port >= 1 && port <= 65535;
        } catch (IOException | NumberFormatException e) {
            return false;
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("port-probe-", ".txt");
        try {
            Files.write(file, "8080\n".getBytes(StandardCharsets.UTF_8));
            System.out.println(validPort(file));

            Files.write(file, "oops\n".getBytes(StandardCharsets.UTF_8));
            System.out.println(validPort(file));
        } finally {
            Files.deleteIfExists(file);
        }
        System.out.println(validPort(file));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ErrorPolicyProbe.java
java ErrorPolicyProbe
```

Kết quả:

```text
true
false
false
```

Ba dòng lần lượt tương ứng với **dữ liệu hợp lệ**, **dữ liệu không phải số** và **tệp đã bị xóa**. Có thể bổ sung ca `0` và `65536` (đều `false`), hoặc `65535` (`true`) để kiểm tra biên.

**Điểm quyết định:** Multi-catch là phù hợp **chỉ vì** hợp đồng yêu cầu cùng phản ứng. Nếu đây là cấu hình bắt buộc của server, việc gộp “không mở được file” và “giá trị sai” thành `false` có thể che mất nguyên nhân vận hành. Khi cần log, thông điệp hoặc cách khôi phục khác nhau, hãy tách các `catch` và giữ thông tin gốc.

Hai loại exception trong cùng multi-catch không được có quan hệ cha–con (ví dụ `IOException` và `FileNotFoundException` không được ghép vì một loại là lớp con của loại kia). Biến exception của multi-catch không thể gán lại.

## 5. Thí nghiệm C — Kiểm tra exception khi chính việc đóng tài nguyên thất bại

**Bài toán:** Nếu công việc phát sinh lỗi và `close()` cũng phát sinh lỗi, ta cần giữ được nguyên nhân chính.

**Lựa chọn:** `try-with-resources` lưu lỗi xảy ra khi đóng tài nguyên thành **suppressed exception** trên exception chính, thay vì làm mất dấu lỗi của phần công việc.

Lưu thành `SuppressedProbe.java`:

```java
public final class SuppressedProbe {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new IllegalStateException("work failed");
        } catch (IllegalStateException e) {
            System.out.println("primary: " + e.getMessage());
            System.out.println("suppressed: " + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SuppressedProbe.java
java SuppressedProbe
```

Kết quả:

```text
primary: work failed
suppressed: close failed
```

**Ý nghĩa:** Phần công việc thất bại trước; `close()` vẫn được gọi; lỗi đóng tài nguyên được lấy qua `getSuppressed()`. Trong ứng dụng thật, khi ghi log exception, cần giữ cả chuỗi nguyên nhân và suppressed exceptions. Nếu khai báo nhiều tài nguyên trong cùng `try`, chúng được đóng theo thứ tự ngược với lúc khai báo.

Đừng hiểu `try-with-resources` là cơ chế tự xử lý mọi ngoại lệ. Nó **quản lý việc đóng**; chính sách bắt, ghi log, retry hay trả lỗi cho người gọi vẫn do bài toán quyết định.

## 6. Thí nghiệm D — Diamond operator để giảm lặp kiểu generic

**Bài toán:** Lưu danh sách điểm số theo tên nhóm, đồng thời muốn trình biên dịch giúp phát hiện việc thêm sai kiểu dữ liệu.

**Lựa chọn:** Giữ kiểu đầy đủ ở biến, rút gọn phần tạo đối tượng bằng `<>`. Diamond operator cho phép trình biên dịch suy luận đối số kiểu từ ngữ cảnh.

Lưu thành `DiamondProbe.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class DiamondProbe {
    public static void main(String[] args) {
        Map<String, List<Integer>> groups = new HashMap<>();
        List<Integer> values = new ArrayList<>();
        values.add(7);
        groups.put("sample", values);
        System.out.println(groups.get("sample").get(0) * 2);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 DiamondProbe.java
java DiamondProbe
```

Kết quả:

```text
14
```

**Thử phản chứng:** Thêm dòng `values.add("wrong");` rồi biên dịch lại. Trình biên dịch phải báo lỗi kiểu dữ liệu vì `values` là `List<Integer>`. Khôi phục dòng đó để chương trình chạy tiếp. Generic giúp kiểm tra lúc biên dịch; diamond **không** thay đổi thuật toán, cấu trúc dữ liệu hay cơ chế type erasure tại runtime.

Trong dự án thực tế, thường khai báo theo interface (`Map`, `List`) và chọn implementation (`HashMap`, `ArrayList`) theo yêu cầu về thứ tự, tra cứu và đồng thời; ký hiệu `<>` không tự quyết định các đặc tính này.

## 7. Những lựa chọn khác vẫn có giá trị, nhưng không phải mặc định

- **`switch` với `String`:** Hữu ích khi một chuỗi chọn một trong ít nhánh rõ ràng (chẳng hạn `"read"`, `"write"`). Trên cú pháp `switch` truyền thống, chú ý `break`/`return` để tránh rơi sang nhánh kế, sự phân biệt hoa–thường và trường hợp giá trị `null` gây `NullPointerException`. Trên JDK hiện đại, xem xét `switch expression` khi nó làm ý nghĩa rõ hơn; đừng ép code mới dùng cấu trúc cũ chỉ vì đang học Java 7.
- **Literal nhị phân và dấu `_` trong số:** `int mask = 0b0101_0000;` biểu diễn số `80`, và `long budget = 1_000_000L;` giúp đọc một triệu dễ hơn. Dấu `_` chỉ là cách viết literal, không thay đổi giá trị; nó phải đặt ở vị trí hợp lệ giữa các chữ số.
- **`ForkJoinPool`:** Phù hợp cho một số thuật toán chia để trị có công việc CPU đủ lớn và có thể tách rồi gộp. Hãy đo với dữ liệu đại diện, kiểm tra overhead và khả năng dùng chung tài nguyên; không tự suy luận “chạy song song luôn nhanh hơn”. Với thao tác I/O chặn, chọn mô hình thực thi dựa trên tính chất I/O và JDK đang dùng.

## 8. Ma trận test tối thiểu cho các thí nghiệm

| Thí nghiệm | Đầu vào/biến thể | Kỳ vọng | Điều nó chứng minh |
| --- | --- | --- | --- |
| `FileProbe` | `alpha\nbeta\n` | `lines=2` | Đọc tuần tự và giải phóng reader |
| `FileProbe` | Chuỗi rỗng | `lines=0` | Điều kiện kết thúc vòng lặp |
| `FileProbe` | Thêm `gamma\n` | `lines=3` | Kết quả phụ thuộc dữ liệu thật |
| `ErrorPolicyProbe` | `8080` | `true` | Ca hợp lệ |
| `ErrorPolicyProbe` | `oops` hoặc mất file | `false` | Chính sách gom lỗi của ví dụ |
| `ErrorPolicyProbe` | `0`, `65535`, `65536` | `false`, `true`, `false` | Biên của miền giá trị |
| `SuppressedProbe` | Body và close cùng ném exception | `work failed` chính, `close failed` suppressed | Giữ được ngữ cảnh lỗi |
| `DiamondProbe` | Thêm `Integer` rồi biên dịch | In `14` | Kiểu generic hợp lệ |
| `DiamondProbe` | Thêm `String` vào `List<Integer>` | Không biên dịch | Bắt lỗi kiểu trước khi chạy |

Khi test được viết theo “đầu vào → kỳ vọng → quan sát”, người học dễ tách **hành vi ngôn ngữ/API** khỏi giả định của mình. Nếu kết quả trái kỳ vọng, kiểm tra lại tiền điều kiện, bản JDK, dữ liệu, hệ điều hành và chính sách xử lý lỗi trước khi kết luận tính năng sai.

## 9. Lỗi lựa chọn thường gặp và cách sửa

1. **Chọn tính năng vì nó mới hoặc ngắn hơn:** Code ngắn chưa chắc rõ; giải thích bằng tiêu chí cụ thể (“đóng tài nguyên kể cả khi lỗi”, “bắt sai kiểu lúc biên dịch”).
2. **Dùng `Files.exists(path)` làm bảo đảm rồi mới thao tác:** Giữa lúc kiểm tra và đọc/ghi, file có thể thay đổi. Hãy thực hiện thao tác và xử lý lỗi thực tế.
3. **Bỏ charset khi xử lý văn bản:** Dữ liệu có dấu có thể khác nhau giữa môi trường. Chọn charset theo hợp đồng, ví dụ `StandardCharsets.UTF_8`.
4. **Gộp mọi lỗi vào một `catch`:** Trước tiên hỏi người gọi có cần phân biệt lỗi thiếu file, lỗi quyền, dữ liệu lỗi và lỗi lập trình không. Không bắt `Exception` tràn lan để biến tất cả thành thành công giả.
5. **Lầm rằng `try-with-resources` tự xóa file hoặc tự rollback:** Nó gọi `close()` cho tài nguyên phù hợp; xóa file, commit/rollback và xử lý lỗi vẫn phải được thiết kế rõ.
6. **Lầm rằng `<>` làm collection an toàn hơn về đồng thời:** Generic là kiểm tra kiểu; đồng bộ hóa, thứ tự và hiệu năng thuộc về kiểu collection/thiết kế truy cập.
7. **Thấy một lần chạy nhanh rồi kết luận tối ưu:** Với xử lý song song phải có dữ liệu đủ lớn, đo nhiều lần, kiểm soát warm-up và so sánh cùng điều kiện.
8. **Chỉ kiểm tra happy path:** Mọi ví dụ nên có ít nhất một trường hợp sai và một trường hợp biên để phát hiện giả định ẩn.

## 10. Checklist áp dụng vào một yêu cầu thật

Trước khi đưa giải pháp vào codebase, hãy trả lời được:

- **Yêu cầu:** Đầu vào/đầu ra, ràng buộc dữ liệu, lỗi cần phân biệt và tài nguyên cần đóng là gì?
- **Lựa chọn:** Tính năng đang xử lý đúng rủi ro nào? Có phương án tiêu chuẩn đơn giản hơn không?
- **Bằng chứng:** Có chương trình nhỏ chạy trên JDK hiện dùng, lệnh chạy, kết quả mong đợi và ca lỗi/biên không?
- **Độ tin cậy:** Có xử lý I/O, charset, cleanup, exception và kiểm tra kiểu phù hợp không?
- **Khả năng mở rộng:** Khi dữ liệu lớn hơn hoặc concurrency tăng, cần đo, kiểm thử hay thay đổi thiết kế gì?
- **Kết luận:** Tại sao lựa chọn này phù hợp với **bài toán cụ thể**, chứ không chỉ vì nó là tính năng của Java 7?

**Ví dụ kết luận kỹ thuật tốt:** “Tôi chọn `Path`/`Files` để thao tác file và `try-with-resources` để đóng reader; thử với hai dòng, file trống và lỗi đọc. Giải pháp đáp ứng yêu cầu đọc tuần tự và quản lý tài nguyên. Nếu chuyển sang đọc file cực lớn hoặc format phức tạp, cần đánh giá lại chiến lược xử lý đầu vào.”

## Tài liệu chính thức để đối chiếu

- [Oracle — Java SE 7 Language Enhancements](https://docs.oracle.com/javase/7/docs/technotes/guides/language/enhancements.html): xác định các tính năng ngôn ngữ được bổ sung trong Java 7.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng đóng tài nguyên trong JDK hiện đại.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): API thao tác hệ tệp, ngoại lệ và hành vi I/O.
- [Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): mô hình thực thi cho tác vụ có thể chia nhỏ.

Các kỹ thuật được dùng trong bài vẫn có ý nghĩa trên JDK hiện đại; quyết định áp dụng luôn phụ thuộc vào hành vi cần chứng minh và các giới hạn thực tế của bài toán.