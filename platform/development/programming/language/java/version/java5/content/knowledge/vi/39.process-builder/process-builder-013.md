# Quản lý quyền sở hữu và đóng các luồng I/O

## 1. Một tiến trình con có hai vòng đời cần quản lý

Khi gọi `ProcessBuilder.start()`, chương trình không chỉ tạo ra một tiến trình con. Nếu dùng cấu hình pipe mặc định, nó còn nhận các đầu kênh I/O để giao tiếp với tiến trình đó.

Có hai nhóm trách nhiệm:

1. **Vòng đời tiến trình:** ai chờ kết thúc, đặt thời hạn hoặc yêu cầu dừng?
2. **Vòng đời các đầu kênh:** ai ghi, ai đọc, khi nào gửi EOF và khi nào đóng?

Hai nhóm liên quan nhưng không đồng nhất. Đóng một luồng I/O không tự có nghĩa tiến trình đã kết thúc. Một tiến trình kết thúc cũng không phải lý do để bỏ qua việc đóng các đối tượng đọc/ghi mà mã đang giữ.

Quyền sở hữu ở đây nghĩa là một thành phần chịu trách nhiệm kết thúc việc dùng tài nguyên và thu hồi nó đúng lúc. Thành phần khác có thể được mượn để đọc/ghi mà không được tự đóng.

Bài dùng ProcessBuilder và các API vẫn áp dụng trong Java hiện đại; ví dụ chạy trên JDK 17 trở lên.

## 2. Đọc đúng chiều của ba phương thức

Tên các phương thức được nhìn từ chương trình Java cha, không phải từ tiến trình con:

| Phương thức của Process | Kiểu phía cha | Nối với phía con | Trách nhiệm thường gặp |
| --- | --- | --- | --- |
| `getOutputStream()` | OutputStream | stdin của con | Ghi yêu cầu; đóng khi không còn dữ liệu gửi |
| `getInputStream()` | InputStream | stdout của con | Đọc/thoát đầu ra rồi đóng |
| `getErrorStream()` | InputStream | stderr của con | Đọc/thoát lỗi riêng rồi đóng |

Hình dung:

```text
Cha: OutputStream ───────────→ Con: stdin

Cha: InputStream  ←─────────── Con: stdout

Cha: InputStream  ←─────────── Con: stderr
```

Một lỗi đặt tên biến thường dẫn đến hiểu sai: gọi `getOutputStream()` rồi đặt biến là outputOfChild. Thực tế đó là nơi cha ghi **vào** con. Các tên như `toChild`, `fromChild`, `errorFromChild` thường rõ chiều hơn.

ProcessBuilder chỉ mô tả cấu hình và khởi chạy. Đối tượng Process và các stream nhận được mới đại diện cho lần chạy cụ thể. Dùng một builder để start nhiều lần tạo ra nhiều nhóm tài nguyên độc lập.

## 3. Đóng stdin là một tín hiệu giao thức

Giả sử tiến trình con đọc cho đến hết đầu vào rồi mới tính kết quả.

Nếu cha chỉ ghi và flush nhưng không đóng đầu ghi, con có thể vẫn chờ dữ liệu:

```text
Cha: ghi xong → đợi con kết thúc
Con: chưa thấy EOF → đợi cha gửi tiếp
```

Đây là vòng chờ do giao thức chưa được kết thúc.

Khi cha hoàn tất dữ liệu của một giao thức đọc đến EOF:

```java
try (OutputStream toChild = process.getOutputStream()) {
    toChild.write(requestBytes);
}
```

Đây là đoạn minh họa có process và requestBytes đã được tạo. Khi thoát khối, đầu ghi được đóng; phía con có thể quan sát EOF sau khi đã đọc hết byte còn lại.

Flush và close không cùng nghĩa:

- Flush đẩy dữ liệu đang đệm theo hợp đồng lớp ghi.
- Close kết thúc việc dùng đầu kênh và giải phóng tài nguyên tương ứng.
- Với pipe đầu vào của con, đóng đầu ghi cũng giúp báo không còn dữ liệu gửi.

Không tự đóng đầu ghi sau mỗi dòng nếu giao thức còn nhiều lượt yêu cầu/đáp ứng. Khi dùng giao thức tương tác, cần xác định ranh giới bản tin bằng quy tắc riêng; EOF thường là kết thúc toàn bộ chiều gửi đó.

Nếu không gửi gì cho một tiến trình vốn đang chờ stdin, đóng đầu ghi ngay có thể cần thiết để nó biết đầu vào rỗng đã kết thúc. Việc không viết không đồng nghĩa EOF.

## 4. Đọc hết stdout và stderr trước khi bỏ chúng

Các pipe có bộ đệm hữu hạn. Nếu con ghi quá nhiều mà cha không đọc, con có thể bị chặn vì không còn chỗ.

Do đó mẫu sau có rủi ro:

```java
// Không phải thứ tự an toàn tổng quát cho tiến trình tạo nhiều đầu ra.
int exit = process.waitFor();
String text = new String(process.getInputStream().readAllBytes());
```

Con có thể chưa thoát vì đang chờ cha rút bớt dữ liệu; cha lại chờ con thoát trước khi đọc.

Hai chiến lược thường dùng:

- Giữ stdout và stderr riêng, đọc thoát cả hai đồng thời bằng các tác vụ có vòng đời rõ ràng.
- Gộp stderr vào stdout bằng `redirectErrorStream(true)`, rồi đọc một kênh nếu không cần tách hai loại dữ liệu.

Không đọc hết stdout rồi mới bắt đầu đọc stderr như một giải pháp phổ quát. stderr có thể đầy trong khi cha đang đợi stdout kết thúc.

Đọc/thoát có thể là ghi ra tệp, chuyển đến một nơi nhận hoặc thu nhận giới hạn dung lượng; không nhất thiết gom toàn bộ vào một String. Với tiến trình ngoài không kiểm soát, `readAllBytes()` có thể dùng bộ nhớ quá lớn hoặc chờ mãi nếu nguồn không đóng.

## 5. Lớp bọc và quyền đóng nguồn bên dưới

Khi dùng BufferedReader, InputStreamReader hoặc BufferedWriter, cần nhìn cả chuỗi:

```text
BufferedReader
      ↓
InputStreamReader
      ↓
đầu đọc pipe của tiến trình
```

Đóng lớp bọc ngoài thông thường kéo theo đóng nguồn mà nó bọc. Vì vậy nên chọn một điểm sở hữu rõ ràng, thay vì để nhiều tầng đều có thể tùy ý đóng.

Ví dụ một tác vụ chuyên đọc stdout có thể sở hữu reader và đóng nó khi hết dữ liệu. Hàm xử lý từng dòng chỉ nhận dòng String, không cần biết hoặc đóng nguồn.

Ngược lại, một hàm nhận reader được mượn từ tầng điều phối nên tuân thủ hợp đồng “đọc nhưng không đóng” nếu tầng điều phối còn dùng nó.

Đừng trộn một reader có bộ đệm với các lần đọc trực tiếp từ stream bên dưới. Reader có thể đã đọc trước byte mà lần đọc trực tiếp mong đợi. Cũng không tạo hai bộ đọc độc lập trên cùng một pipe rồi hy vọng chúng tự chia dòng đúng ý định.

## 6. Ví dụ chạy được: gửi EOF, đọc kênh gộp và đóng

Chương trình tự chạy một bản Java con của chính lớp đó. Con đọc hai dòng đến EOF, rồi mới ghi hai dòng kết quả. Mẫu này có dữ liệu gửi nhỏ và đầu ra hữu hạn đã biết.

Lưu thành `ProcessIoOwnershipDemo.java`:

```java
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

public class ProcessIoOwnershipDemo {
    private static void child() throws Exception {
        int lines = 0;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
            while (reader.readLine() != null) {
                lines++;
            }
        }

        System.out.write(("child-lines=" + lines + "\n")
                .getBytes(StandardCharsets.UTF_8));
        System.out.flush();
        System.err.write("child-diagnostic\n"
                .getBytes(StandardCharsets.UTF_8));
        System.err.flush();
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("child")) {
            child();
            return;
        }

        String executable = System.getProperty("os.name")
                .startsWith("Windows") ? "java.exe" : "java";
        String java = Path.of(
                System.getProperty("java.home"), "bin", executable).toString();

        Process process = new ProcessBuilder(
                java,
                "-cp", System.getProperty("java.class.path"),
                ProcessIoOwnershipDemo.class.getName(),
                "child")
                .redirectErrorStream(true)
                .start();

        try (OutputStream toChild = process.getOutputStream();
             InputStream fromChild = process.getInputStream();
             InputStream separateError = process.getErrorStream()) {
            try {
                toChild.write("one\ntwo\n"
                        .getBytes(StandardCharsets.UTF_8));
                toChild.close();

                String merged = new String(
                        fromChild.readAllBytes(), StandardCharsets.UTF_8);
                int exit = process.waitFor();

                System.out.println("merged="
                        + merged.lines().collect(Collectors.joining(" / ")));
                System.out.println("exit=" + exit);
            } finally {
                if (process.isAlive()) {
                    process.destroyForcibly();
                    if (!process.waitFor(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Child did not terminate");
                    }
                }
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 ProcessIoOwnershipDemo.java
java ProcessIoOwnershipDemo
```

Stdout của lần chạy bình thường:

```text
merged=child-lines=2 / child-diagnostic
exit=0
```

### Những điểm về quyền sở hữu trong ví dụ

- Cha tạo Process nên nhận trách nhiệm với các đầu kênh pipe phía cha.
- `toChild.close()` xảy ra ngay sau hai dòng, không đợi đến cuối khối. Đây là thời điểm phải gửi EOF để con đi tiếp.
- try-with-resources ở ngoài vẫn bảo đảm đầu kênh được đóng nếu một bước trước đó ném lỗi. Đóng lại một stream đã đóng theo hợp đồng Closeable không tạo một lượt gửi mới.
- stderr được gộp trước start, nên `fromChild` đọc cả hai dòng. `separateError` là đầu đọc rỗng đặc biệt trong cấu hình này, không phải một kênh stderr thứ hai chứa dữ liệu cần thu lại.
- Cha đọc hết dữ liệu rồi thu mã thoát. Khối finally yêu cầu dừng con nếu đường xử lý ra ngoài khi con còn sống.
- Việc tạo câu lệnh bằng danh sách đối số không cần ghép một chuỗi lệnh shell hoặc tự thêm dấu nháy quanh classpath có khoảng trắng.

Trong tiến trình con, nhánh child là toàn bộ chương trình của nó nên nhánh đó sở hữu việc đọc đến cuối System.in. Điều này khác với một hàm thư viện bên cha tùy tiện đóng đầu vào chuẩn dùng chung.

### Giới hạn có chủ ý của ví dụ

Thứ tự “ghi hết rồi đọc hết” chỉ phù hợp ở đây vì dữ liệu gửi rất nhỏ và con không ghi kết quả cho đến khi nhận EOF. Không mở rộng thành quy tắc cho một chương trình tương tác hoặc trao đổi dữ liệu lớn hai chiều.

Ví dụ cũng không đặt thời hạn bao trùm lần readAllBytes và waitFor bình thường. Mốc năm giây trong finally chỉ dành cho bước xác nhận dừng cưỡng bức ở đường dọn dẹp; nó không làm lần đọc trước đó tự có timeout.

Với tiến trình ngoài có thể treo hoặc sinh dữ liệu không giới hạn, cần bộ điều phối có thời hạn tổng thể, bộ đọc có giới hạn lưu trữ và chính sách dừng/đóng đủ để giải phóng các tác vụ I/O.

## 7. Chuyển hướng làm thay đổi đầu kênh mà cha quản lý

Nếu dùng redirectInput từ tệp, cha không còn một pipe stdin thông thường để ghi. Phương thức getOutputStream trả một output stream đặc biệt: ghi sẽ lỗi, close không có tác dụng.

Tương tự, khi redirectOutput hoặc redirectError sang nơi khác, đầu đọc tương ứng trả stream đặc biệt luôn báo hết dữ liệu, không phải nội dung của tệp đã chuyển hướng.

Các trường hợp cần phân biệt:

| Cấu hình | Cha cần làm gì? |
| --- | --- |
| PIPE mặc định | Quản lý đầu ghi/đọc mà Process cung cấp |
| Gộp stderr vào stdout | Một đầu đọc dữ liệu gộp; không cố thu stderr riêng lần nữa |
| Chuyển đầu ra sang tệp | Quản lý chính sách tệp; không chờ nội dung từ pipe đã không còn |
| Kế thừa I/O bằng inheritIO | Tôn trọng các tài nguyên chuẩn được chia sẻ/kế thừa; không tự đóng System.out/System.err của cha |

Các stream đặc biệt này là đối tượng stream có hành vi quy định, không phải giá trị null Java. Kiểm tra cấu hình chuyển hướng mới cho biết vì sao đọc được EOF ngay.

Nếu đầu ra đã được chuyển sang tệp, việc đọc tệp sau đó là một vòng đời khác. Cha mở một reader riêng để kiểm tra tệp thì chính cha phải đóng reader đó; không coi getInputStream là cách đọc lại tệp chuyển hướng.

## 8. Chờ tiến trình và đóng kênh là hai bằng chứng khác nhau

Ba quan sát không được đánh đồng:

1. **Ghi xong yêu cầu:** có thể còn dữ liệu đệm hoặc con còn đang xử lý.
2. **Đã đọc đến EOF:** kênh đó không còn dữ liệu theo trạng thái hiện tại; chưa tự giải thích mã thoát.
3. **Process đã kết thúc:** có mã thoát, nhưng vẫn cần hoàn tất việc thu nhận/dọn dẹp I/O theo thiết kế.

Nếu một tiến trình con khác hoặc hậu duệ còn giữ đầu ghi của pipe, việc Process trực tiếp kết thúc chưa nhất thiết làm bên đọc thấy EOF ngay. Vì vậy, chỉ đặt timeout cho waitFor không tự bảo đảm tác vụ đọc cũng kết thúc.

Tương tự, mất tham chiếu tới Process hoặc đợi bộ thu gom rác không phải chính sách dừng. Tiến trình native có thể tiếp tục chạy dù mã Java không còn giữ biến đại diện cho nó.

Khi cần theo dõi cả cây tiến trình, phải có chính sách riêng cho hậu duệ và giới hạn của hệ điều hành. Dừng Process trực tiếp không tự chứng minh mọi tiến trình nó từng tạo đều đã bị dừng.

## 9. Thiết kế đường lỗi và hủy có một bên điều phối

Với mã chạy một công cụ ngoài thực tế, nên xác định trước:

- Ai sở hữu Process?
- Ai sở hữu mỗi đầu kênh hoặc lớp bọc?
- Ai là người duy nhất quyết định ngừng gửi?
- Nếu reader lỗi, ai báo để người điều phối dừng tiến trình?
- Nếu hết thời gian, ai yêu cầu dừng và chờ xác nhận?
- Khi nào được đóng kênh trong lúc tác vụ khác đang đọc?
- Ai chờ các tác vụ I/O kết thúc và thu ngoại lệ của chúng?

Đóng sớm đầu đọc có thể khiến con gặp lỗi ghi hoặc chỉ thấy việc giao tiếp bị ngắt, tùy chương trình và nền tảng. Đó không phải một cách “bỏ qua output” miễn phí. Nếu chủ ý không dùng output, cân nhắc chuyển hướng phù hợp từ trước khi start.

Ở đường hủy, một thứ tự phải được chọn theo giao thức và nền tảng: ngừng gửi, yêu cầu tiến trình kết thúc, tiếp tục thu hoặc chủ động đóng các kênh cần thiết, rồi chờ các tác vụ phụ kết thúc. Không có một lệnh close đơn lẻ thay cho toàn bộ quy trình.

Ngắt một luồng Java cũng không bảo đảm mọi kiểu đọc InputStream lập tức bị ngắt. Cần biết hợp đồng của kênh đang dùng; đôi khi việc kết thúc tiến trình hoặc đóng đầu kênh là phần cần thiết để việc đọc thoát.

Nếu dọn dẹp phát sinh lỗi, giữ được lỗi gốc và những lỗi phụ để chẩn đoán. try-with-resources hỗ trợ ghi nhận ngoại lệ đóng tài nguyên dưới dạng suppressed exception; mã finally bổ sung cũng cần tránh vô tình che mất nguyên nhân chính trong một bộ điều phối đầy đủ.

## 10. Không đóng tài nguyên được mượn

Một tiện ích có thể được giao đích ghi như `System.out`, một Writer chung hoặc bộ ghi log. Nếu nó chỉ được quyền đưa dữ liệu vào đó, không tự close đích khi một tiến trình con xong.

Ví dụ thiết kế tốt là phân biệt:

```text
Đầu đọc pipe: thuộc lần chạy con → tiện ích có thể đóng theo hợp đồng.
Đích nhận log: do ứng dụng truyền vào → tiện ích chỉ ghi, không đóng.
```

Nếu dùng transferTo để chuyển dữ liệu sang một đích chung, cũng phải xét quyền sở hữu hai đầu riêng. Việc một API chuyển dữ liệu kết thúc không tự cấp quyền kết thúc toàn bộ vòng đời đích.

Các quy tắc này giúp một lỗi I/O ở tiến trình con không kéo theo việc đóng nhầm console hoặc log của cả ứng dụng.

## 11. Tự kiểm tra

1. getOutputStream của Process nối với stdout hay stdin của con?
2. Flush có thay được EOF cho một con đọc đến hết đầu vào không?
3. Vì sao waitFor trước khi đọc output có thể gây vòng chờ?
4. Khi đã redirectErrorStream(true), có cần đọc một stderr đầy đủ riêng nữa không?
5. Một helper nhận Writer dùng chung có nên tự đóng nó khi xử lý xong một con không?
6. Process trực tiếp đã thoát có chứng minh mọi reader đều đã thấy EOF không?
7. Mốc timeout trong khối dọn dẹp có tự giới hạn thời gian readAllBytes ở trước không?

Đáp án:

1. Nối stdin của con.
2. Không; còn phải kết thúc chiều gửi theo giao thức.
3. Con có thể đang bị chặn vì pipe đầy và cần cha đọc.
4. Không; stderr đã đi chung đích stdout.
5. Không, trừ khi hợp đồng đã chuyển quyền sở hữu.
6. Không; còn phụ thuộc đầu kênh khác/hậu duệ và cấu hình.
7. Không; thời hạn phải bao trùm đúng thao tác cần giới hạn.

Mỗi lần chạy nên có một chủ sở hữu vòng đời rõ ràng, còn mỗi kênh phải có một kế hoạch đọc/ghi và đóng riêng. Khi các ranh giới đó nhất quán, việc gửi EOF, thu đầu ra và dừng tiến trình mới phối hợp được với nhau.

## Tài liệu đối chiếu

- [Process — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Process.html): ba đầu kênh, nguy cơ chặn, vòng đời tiến trình và tài nguyên.
- [ProcessBuilder — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ProcessBuilder.html): cấu hình PIPE, chuyển hướng và gộp stderr.
