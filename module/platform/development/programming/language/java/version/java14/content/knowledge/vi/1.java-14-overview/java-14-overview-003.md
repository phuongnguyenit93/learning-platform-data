# Java 14: Phân biệt mốc giới thiệu với mốc trở thành tính năng chính thức

## Mục tiêu

Sau bài này, bạn có thể:
- Giải thích vì sao câu “tính năng X có trong Java 14” chưa đủ để kết luận X đã là tính năng chuẩn ở Java 14.
- Phân biệt **lần xuất hiện đầu tiên**, **preview lần đầu/lần tiếp theo** và **bản chính thức (standard/permanent)** dựa trên tài liệu phát hành và JEP.
- Xác định đúng các mốc của `switch expressions`, `records`, pattern matching cho `instanceof` và `text blocks`.
- Đọc mã Java hiện đại dựa trên phiên bản mà từng tính năng đã trở thành chuẩn, tránh áp dụng lại cú pháp preview cũ.

## 1. “Giới thiệu” không đồng nghĩa với “chính thức”

Một tính năng có thể đi qua nhiều bản phát hành trước khi trở thành một phần chuẩn của ngôn ngữ hoặc API:

1. **Lần xuất hiện đầu tiên**: phiên bản JDK đầu tiên cung cấp tính năng để người dùng thử hoặc sử dụng. Cần ghi kèm trạng thái ở thời điểm đó, chẳng hạn **Preview**.
2. **Preview**: tính năng đã có đặc tả và triển khai để thử nghiệm, nhưng thiết kế còn có thể điều chỉnh sau phản hồi. Tính năng preview của ngôn ngữ/VM phải được bật tường minh khi biên dịch và chạy. Preview có thể được phát hành lại, được chuẩn hóa hoặc bị rút bỏ; không có cam kết mọi preview đều trở thành chính thức.
3. **Standard / Permanent (chính thức)**: phiên bản ngôn ngữ đã nhận tính năng làm thành phần chuẩn. Mã dùng đúng phiên bản chuẩn không còn cần cờ preview dành cho tính năng đó. Từ đây, các quy tắc tương thích thông thường của Java áp dụng cho tính năng đã chuẩn hóa.

Vì vậy, hãy hỏi hai câu riêng biệt:

- **Tính năng được giới thiệu lần đầu ở JDK nào, với trạng thái gì?**
- **Tính năng trở thành chuẩn ở JDK nào?**

Ví dụ, “`records` xuất hiện trong Java 14” là đúng nếu hiểu là **preview lần đầu**; nói “`records` là tính năng chuẩn từ Java 14” là sai. Mốc chuẩn là **Java 16**.

**Lưu ý về thuật ngữ:** Java 14 còn có các thay đổi thư viện, công cụ, VM và các API ở trạng thái thử nghiệm khác nhau. Không thể suy ra trạng thái preview/chính thức của mọi JEP chỉ từ số phiên bản; phải xem **tên, trạng thái và lịch sử của chính JEP đó**.

## 2. Bảng mốc cần nhớ khi nhìn lại Java 14

| Tính năng | Lần xuất hiện đầu tiên | Trạng thái trong Java 14 | Mốc trở thành chuẩn | JEP xác nhận mốc chuẩn |
|---|---|---|---|---|
| **Switch expressions** (`switch` trả về giá trị) | Java 12 — Preview; Java 13 — Preview lần hai | **Chính thức ngay tại Java 14** | **Java 14** | [JEP 361](https://openjdk.org/jeps/361) |
| **Records** (`record`) | **Java 14 — Preview lần đầu** | Preview; Java 15 tiếp tục Preview | **Java 16** | [JEP 395](https://openjdk.org/jeps/395) |
| **Pattern matching cho `instanceof`** | **Java 14 — Preview lần đầu** | Preview; Java 15 tiếp tục Preview | **Java 16** | [JEP 394](https://openjdk.org/jeps/394) |
| **Text blocks** (chuỗi nhiều dòng `"""`) | Java 13 — Preview lần đầu | **Preview lần hai trong Java 14** | **Java 15** | [JEP 378](https://openjdk.org/jeps/378) |

Ba kết luận khác nhau đều có thể đúng về Java 14:

- **“Được giới thiệu tại Java 14”**: đúng với `records` và pattern matching cho `instanceof`, nhưng phải ghi rõ **preview**.
- **“Được cải tiến/preview lại tại Java 14”**: đúng với `text blocks`, vốn xuất hiện trước đó ở Java 13.
- **“Trở thành chính thức tại Java 14”**: đúng với `switch expressions`, vốn đã được preview từ Java 12.

### 2.1. Switch expressions — Java 14 là mốc chuẩn, không phải mốc đầu tiên

- Java 12: [JEP 325](https://openjdk.org/jeps/325) — Preview lần đầu.
- Java 13: [JEP 354](https://openjdk.org/jeps/354) — Preview lần hai; cách trả giá trị được điều chỉnh theo hướng dùng `yield`.
- **Java 14: [JEP 361](https://openjdk.org/jeps/361) — chuẩn hóa.**

Cú pháp chuẩn hiện nay:

~~~java
String level = switch (score) {
    case 10 -> "Excellent";
    case 9, 8 -> "Good";
    default -> "Other";
};
~~~

Đây là **đoạn mã minh họa**, giả sử biến `score` là một `int` đã được khai báo. `switch` lúc này là biểu thức trả về một giá trị; dạng mũi tên `->` không fall through. Khi một nhánh dùng khối lệnh và cần trả giá trị, dùng `yield`. Không sử dụng các biến thể cú pháp từ bản preview Java 12 trong mã mới.

### 2.2. Records — giới thiệu Java 14, chính thức Java 16

- **Java 14: [JEP 359](https://openjdk.org/jeps/359) — Preview lần đầu.**
- Java 15: [JEP 384](https://openjdk.org/jeps/384) — Preview lần hai.
- **Java 16: [JEP 395](https://openjdk.org/jeps/395) — chính thức.**

`record` giúp khai báo lớp mang dữ liệu ngắn gọn. Trình biên dịch sinh constructor chuẩn, các phương thức truy cập component, `equals`, `hashCode` và `toString` thích hợp. Record có tính bất biến ở cấu trúc component (**shallow immutability**): các tham chiếu component không thể gán lại sau khi khởi tạo, nhưng đối tượng mutable được tham chiếu bên trong vẫn có thể thay đổi.

~~~java
record Point(int x, int y) {}

Point p = new Point(3, 5);
System.out.println(p.x()); // 3
~~~

Đây là **đoạn minh họa** để đặt trong phương thức hoặc lớp phù hợp, không phải tệp Java độc lập. Dùng `record` như một tính năng **chuẩn từ Java 16 trở lên**; không cần bật preview trong các bản JDK hiện đại.

### 2.3. Pattern matching cho instanceof — giới thiệu Java 14, chính thức Java 16

- **Java 14: [JEP 305](https://openjdk.org/jeps/305) — Preview lần đầu.**
- Java 15: [JEP 375](https://openjdk.org/jeps/375) — Preview lần hai.
- **Java 16: [JEP 394](https://openjdk.org/jeps/394) — chính thức.**

Cú pháp chuẩn kết hợp kiểm tra kiểu và khai báo biến đã được kiểm tra kiểu:

~~~java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
~~~

Biến `text` chỉ khả dụng ở phạm vi mà trình biên dịch xác định phép kiểm tra kiểu đã thành công (**flow scoping**). Cú pháp này giúp tránh ép kiểu tường minh lặp lại. Chỉ riêng pattern matching cho `instanceof` có mốc chính thức **Java 16**; không được đánh đồng với mọi dạng pattern matching khác trong Java, vốn có vòng đời riêng.

### 2.4. Text blocks — đã có từ Java 13, chính thức Java 15

- Java 13: [JEP 355](https://openjdk.org/jeps/355) — Preview lần đầu.
- **Java 14: [JEP 368](https://openjdk.org/jeps/368) — Preview lần hai.**
- **Java 15: [JEP 378](https://openjdk.org/jeps/378) — chính thức.**

Text block dùng `"""` để biểu diễn chuỗi nhiều dòng, với quy tắc xử lý thụt lề và xuống dòng xác định. Ví dụ mã chuẩn (trong phạm vi khai báo biến hợp lệ):

~~~java
String json = """
        {
          "name": "Java"
        }
        """;
~~~

Vì text blocks đã là tính năng chuẩn từ Java 15, không nên trình bày chúng như một “tính năng mới chỉ có ở Java 14” hay yêu cầu cờ preview khi dùng các JDK hiện nay.

## 3. Ví dụ chạy hoàn chỉnh với các cú pháp đã chính thức

Tệp **`Java14Milestones.java`** dưới đây sử dụng bốn cú pháp trong bảng, nhưng theo **phiên bản chuẩn**, không phụ thuộc vào Java 14 preview. Dùng **JDK 17 trở lên**; `--release 17` quy định mức tương thích nguồn/API của bản biên dịch.

~~~java
public class Java14Milestones {
    record Invoice(String code, int amount) {}

    public static void main(String[] args) {
        Object value = new Invoice("A-14", 200);

        if (value instanceof Invoice invoice) {
            String category = switch (invoice.amount()) {
                case 0 -> "Miễn phí";
                default -> "Có phí";
            };

            String template = """
                    %s | %s | %d
                    """;

            System.out.print(template.formatted(
                    invoice.code(), category, invoice.amount()));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 Java14Milestones.java
java Java14Milestones
~~~

Đầu ra chính xác:

~~~text
A-14 | Có phí | 200
~~~

**Vì sao ví dụ chạy mà không cần `--enable-preview`?** `switch expressions` đã chuẩn từ 14, `text blocks` từ 15, còn `records` và `instanceof` pattern matching từ 16. Tất cả đều chuẩn trong ngôn ngữ Java 17. Ngoài ra, `String.formatted(...)` đã có từ Java 15, nên cũng dùng được với `--release 17`.

**Không suy ngược:** Ví dụ này **không** biên dịch nguyên vẹn với `--release 14`, vì `records`, `instanceof` pattern matching và `text blocks` chưa là tính năng chuẩn tại mốc đó.

## 4. Cách kiểm chứng một mốc tính năng khi đọc tài liệu

Khi gặp câu “Java 14 introduced X”, làm theo thứ tự:

1. **Định danh chính xác X** và JEP tương ứng; tránh gộp hai tính năng có tên gần giống, chẳng hạn `instanceof` pattern matching và pattern matching cho `switch`.
2. **Tìm JEP của lần xuất hiện đầu tiên**; đọc nhãn `Preview`, `Second Preview`, `Incubator` hoặc tên không kèm nhãn đó. “Có trong JDK” chưa đủ để suy ra “chuẩn”.
3. **Theo dõi các JEP nối tiếp** cho cùng tính năng đến mốc `Standard` / `Permanent`; có thể có thay đổi cú pháp hoặc API giữa các giai đoạn.
4. **Đối chiếu tài liệu Java Language Changes by Release** để xác nhận bản phát hành được hỗ trợ chính thức.
5. **Chọn mức `--release` phù hợp với bản chuẩn mà mã sử dụng**. Ví dụ: nếu mã dùng đồng thời `record` và `instanceof String s` ở dạng chuẩn, mức tối thiểu cho hai tính năng này là **Java 16**; nếu yêu cầu môi trường Java 17, `--release 17` là lựa chọn rõ ràng.

### Cờ preview còn có ý nghĩa gì hiện nay?

Với **một tính năng đang ở trạng thái Preview trên JDK đang dùng**, cơ chế hiện hành là bật `--enable-preview` lúc biên dịch cùng mức `--release N` (hoặc `-source N`) ứng với **đúng JDK N**, và bật `--enable-preview` khi chạy bytecode phụ thuộc preview. Preview của bản JDK cũ không tự động trở thành một “chế độ tương thích” có thể bật ở mọi JDK mới.

Với bốn cú pháp **đã chính thức** trong bảng trên, hãy dùng ngôn ngữ chuẩn và biên dịch bình thường; **không thêm `--enable-preview` chỉ vì tài liệu lịch sử Java 14 từng gọi chúng là preview**. Nếu đang nghiên cứu một preview mới khác, phải xem tài liệu của chính phiên bản JDK đó.

## 5. Lỗi diễn giải thường gặp và cách sửa

| Diễn giải dễ sai | Cách diễn giải đúng |
|---|---|
| “Java 14 giới thiệu records, vậy records chính thức từ Java 14.” | Java 14 là **lần preview đầu tiên**; Java 16 mới là **mốc chuẩn**. |
| “Switch expressions ra đời trong Java 14.” | Java 12 là **lần preview đầu tiên**; Java 14 là **mốc chuẩn**. |
| “Text blocks là tính năng mới lần đầu của Java 14.” | Java 13 preview lần đầu, Java 14 preview lần hai, Java 15 chuẩn. |
| “`instanceof String s` có trong Java 14 nên dùng được ở Java 14 mà không cần cờ.” | Java 14 là preview; phiên bản chuẩn không cần cờ bắt đầu từ Java 16. |
| “Tính năng preview chắc chắn sẽ trở thành chuẩn đúng y nguyên.” | Preview có thể được chỉnh sửa, lặp lại hoặc rút khỏi các bản sau. |
| “Bật `--enable-preview` sẽ dùng được cú pháp preview Java 14 ở mọi JDK mới.” | Preview gắn với phiên bản JDK cụ thể; mã mới nên nhắm đến cú pháp đã chuẩn. |

## 6. Tự kiểm tra

**Câu 1.** Một hướng dẫn ghi “Records là tính năng Java 14”. Câu đó thiếu gì?

**Đáp án:** Thiếu **trạng thái khi giới thiệu** (Preview lần đầu ở Java 14) và **mốc chuẩn** (Java 16).

**Câu 2.** Tính năng nào trong bốn tính năng trên **chính thức ngay ở Java 14**?

**Đáp án:** **Switch expressions**, sau hai vòng preview ở Java 12 và Java 13.

**Câu 3.** Cần mốc Java nào để sử dụng **đồng thời** `record`, `instanceof String s`, `switch` expression và text block, tất cả dưới dạng **chuẩn**?

**Đáp án:** **Java 16** là mốc sớm nhất cho cả bốn về mặt tính năng ngôn ngữ. Dùng JDK 17 trở lên khi thực hành như ví dụ.

## Tài liệu đối chiếu

- [Oracle — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): bảng trạng thái của các tính năng theo từng bản Java.
- [Oracle — Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html): vòng đời preview và cơ chế bật preview hiện hành.
- [JEP 12 — Preview Features](https://openjdk.org/jeps/12): quy trình preview.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361); [JEP 395 — Records](https://openjdk.org/jeps/395); [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394); [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): các JEP mốc chuẩn.

**Ghi nhớ:** Luôn nêu **phiên bản + trạng thái**. “Giới thiệu ở Java 14” và “chính thức từ Java 14” là **hai thông tin khác nhau**; hãy đối chiếu lịch sử JEP trước khi kết luận.