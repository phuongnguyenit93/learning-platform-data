# Dùng công cụ định dạng để giảm tranh luận thủ công

Một pull request chỉ sửa công thức tính phí giao hàng, nhưng phần trao đổi lại kéo dài vì những câu hỏi như: “Dấu `{` nên xuống dòng không?”, “Nên dùng bốn dấu cách hay tab?”, “Danh sách tham số dài nên ngắt ở đâu?”, “Import này đặt trước hay sau import kia?”. Hai lập trình viên có thể có sở thích khác nhau và đều đưa ra lý do hợp lý. Nếu mỗi lần review phải quyết định lại những việc như vậy, thời gian thảo luận bị tiêu vào cách trình bày thay vì tính đúng đắn, khả năng bảo trì và rủi ro của thay đổi.

**Công cụ định dạng mã tự động (*code formatter*) giúp chuyển những quyết định có thể chuẩn hóa thành quy tắc được thực thi nhất quán.** Nhóm vẫn cần thống nhất công cụ và chính sách ban đầu, nhưng không phải tranh luận lại từng dấu cách ở mỗi pull request.

Trong chương **Quy ước và nhất quán** thuộc module `CODE_QUALITY_FUNDAMENTALS`, mục tiêu là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Định dạng thống nhất không tự làm thuật toán đúng hoặc thiết kế tốt hơn, nhưng nó giảm nhiễu khi đọc mã, hạn chế thay đổi hình thức không cần thiết và giúp việc review tập trung vào những vấn đề thực chất.

Sau bài học, bạn có thể:

- Phân biệt **định dạng tự động**, **quy ước đặt tên**, **kiểm tra style** và **phân tích chất lượng mã**.
- Nhận diện những tranh luận nên giao cho formatter thay vì xử lý thủ công trong code review.
- Thiết lập nguyên tắc chọn formatter, phiên bản, cấu hình và phạm vi áp dụng thống nhất cho cả nhóm.
- Tổ chức quy trình **format khi phát triển, kiểm tra khi CI**, tránh việc mã định dạng khác nhau giữa các máy.
- Áp dụng công cụ cho mã Java và quản lý các quy ước tệp cơ bản như mã hóa, xuống dòng, khoảng trắng cuối dòng.
- Đưa formatter vào repository cũ mà không tạo một thay đổi khổng lồ khó kiểm tra.
- Biết giới hạn của formatter và vẫn review hành vi, bảo mật, hiệu năng, test và thiết kế.

## 1. Vì sao tranh luận định dạng dễ lặp lại?

Một đoạn mã có nhiều cách trình bày hợp lệ về cú pháp:

```java
class ShippingFee {
long calculate(long subtotal,long fee){
if(subtotal >= 500000){return 0;}
return fee;
}
}
```

Cùng một thuật toán có thể viết dễ đọc hơn:

```java
class ShippingFee {
    long calculate(long subtotal, long fee) {
        if (subtotal >= 500_000) {
            return 0;
        }
        return fee;
    }
}
```

Ở ví dụ trên, việc thụt đầu dòng, chèn khoảng trắng và đặt ngoặc nhọn là **vấn đề định dạng**. Việc thay `500000` bằng `500_000` là thay cách viết literal cho dễ đọc; formatter thông thường **không nhất thiết** tự thực hiện thay đổi đó. Việc chọn tên `subtotal`, `fee`, hay dùng một hằng `FREE_SHIPPING_THRESHOLD_VND` là **vấn đề diễn đạt ý nghĩa**, không thể mặc nhiên giao cho formatter.

Khi không có quy tắc chung, mỗi thành viên có thể vô thức định dạng theo sở thích hoặc cấu hình IDE riêng. Kết quả là:

- Một file được sửa lại về khoảng trắng mỗi khi đổi người bảo trì.
- Pull request chứa nhiều dòng chỉ thay đổi trình bày, làm khó nhìn phần logic thật.
- Review có bình luận lặp đi lặp lại về vị trí dấu ngoặc, import và ngắt dòng.
- Merge conflict phát sinh do cùng đoạn mã bị sửa hình thức ở nhiều nhánh.
- Người mới không biết nên theo phong cách của file hiện tại, dự án khác hay IDE của mình.

Đây là **chi phí phối hợp**. Nó không xuất hiện dưới dạng lỗi chạy chương trình, nhưng làm chậm quá trình thay đổi và tăng số thứ người đọc phải chú ý.

## 2. Format, style, lint và phân tích mã không phải một việc

Bốn loại quy tắc thường bị gộp dưới tên “code style”. Phân biệt chúng giúp giao đúng việc cho đúng công cụ.

| Loại | Câu hỏi cần giải quyết | Ví dụ | Cơ chế phù hợp |
| --- | --- | --- | --- |
| **Formatter** | Mã được trình bày thế nào? | Thụt đầu dòng, ngắt dòng, khoảng trắng, ngoặc, thứ tự import khi công cụ hỗ trợ | Tự động viết lại mã theo quy tắc |
| **Quy ước đặt tên và tổ chức** | Khái niệm được gọi tên và bố trí thế nào? | `calculateTotalVnd`, tên package, trách nhiệm class | Quy ước nhóm, review, một phần có thể lint |
| **Style/linter** | Mã có vi phạm các quy tắc được chọn không? | Import không dùng, đặt tên không đúng quy tắc, quy ước Javadoc | Kiểm tra và báo vi phạm; một số quy tắc có auto-fix |
| **Static analysis / test** | Có dấu hiệu sai hoặc rủi ro không? | Null dereference, truy cập tài nguyên, quy tắc bảo mật, hành vi sai | Phân tích tĩnh, unit/integration test, review |

Một formatter có thể sắp xếp import, nhưng không thể tự biết một tên biến như `x` có diễn đạt tốt ý nghĩa “số tiền đã thanh toán” hay không. Một linter có thể cảnh báo tên phương thức vi phạm quy ước, nhưng không tự chứng minh công thức tiền đúng.

**Mục tiêu phù hợp:** tự động hóa những điều có thể quyết định bằng quy tắc ổn định, giữ con người tập trung vào những quyết định cần hiểu ngữ cảnh.

### Formatter không đồng nghĩa với “clean code”

Mã sau có thể được định dạng rất nhất quán:

```java
boolean valid = x > 0 && y != null && z == 2;
```

Nhưng người đọc vẫn không biết `x`, `y`, `z` đại diện cho cái gì. Một tên hàm rõ nghĩa, kiểu dữ liệu phù hợp và bất biến nghiệp vụ có thể quan trọng hơn sự hoàn hảo của khoảng trắng.

Tương tự, việc formatter chạy thành công không chứng minh mã không có lỗ hổng bảo mật, race condition, truy vấn chậm hay test thiếu.

## 3. Khi nào nên giao quyết định cho công cụ?

Những quy tắc thích hợp để tự động hóa thường có đặc điểm:

1. **Quyết định có thể lặp lại:** cùng một input, phiên bản công cụ và cấu hình sẽ cho kết quả dự kiến giống nhau.
2. **Ít phụ thuộc ngữ nghĩa nghiệp vụ:** không cần hiểu tại sao đơn hàng miễn phí hay không.
3. **Có nhiều điểm sử dụng:** mọi file Java đều gặp quy tắc thụt dòng hoặc import.
4. **Chi phí tranh luận lớn hơn lợi ích cá nhân hóa:** chọn một phong cách chung giảm tổng công duy trì.
5. **Có thể kiểm tra bằng máy:** CI có thể xác nhận mã đã tuân theo quy ước.

Ví dụ những lựa chọn thường được formatter xử lý: khoảng trắng quanh toán tử, thụt dòng, ngắt các biểu thức dài, bố trí dấu ngoặc và một số quy tắc về import.

Những lựa chọn vẫn cần con người: tên lớp có thể hiểu được không, phương thức quá nhiều trách nhiệm không, có cần tách abstraction không, xử lý exception có đúng, thuật toán có hiệu năng phù hợp không.

### Nhất quán không có nghĩa mọi dự án phải dùng cùng một formatter

Một nhóm có thể chọn một style gần với hệ sinh thái hoặc quy tắc đã có. Điều quan trọng là **trong phạm vi repository hoặc module được quản lý, kết quả có thể dự đoán và được tất cả công cụ cùng tôn trọng**.

Không nên đổi formatter liên tục chỉ vì một người thích một kiểu ngắt dòng khác. Khi thay đổi quy tắc, cần có lý do, tác động và kế hoạch chuyển đổi rõ ràng.

## 4. Ví dụ Java: tách sửa logic khỏi sửa cách trình bày

Giả sử yêu cầu là: “Đơn có giá trị từ 500.000 VND trở lên được miễn phí giao hàng; còn lại trả phí 25.000 VND.”

Một phiên bản có hành vi đúng nhưng trình bày không thống nhất:

```java
final class FeePolicy{
private static final long THRESHOLD=500_000L;
long shippingFee(long subtotalVnd){
if(subtotalVnd>=THRESHOLD)
return 0L;
else
return 25_000L;
}
}
```

Sau khi định dạng, ý tưởng vẫn là:

```java
final class FeePolicy {
    private static final long THRESHOLD = 500_000L;

    long shippingFee(long subtotalVnd) {
        if (subtotalVnd >= THRESHOLD) {
            return 0L;
        } else {
            return 25_000L;
        }
    }
}
```

Đoạn sau là **minh họa cách trình bày**, không cam kết chính xác từng dấu ngoặc và dòng trống mà mọi phiên bản formatter đều tạo ra. Một số formatter có thể giữ hoặc đổi những chi tiết khác tùy quy tắc.

Khi review chức năng, người đọc vẫn cần kiểm tra:

- `subtotalVnd` có được âm không?
- Ngưỡng 500.000 VND là quy tắc cố định hay cấu hình?
- Phí 25.000 VND có áp dụng mọi khu vực không?
- Có test ở 499.999 và 500.000 VND không?
- Có thay đổi hành vi nào ngoài yêu cầu không?

**Format giúp bớt một lớp nhiễu để các câu hỏi này nổi bật hơn.** Nó không trả lời thay những câu hỏi đó.

### Tránh “sửa tay cho đẹp hơn” sau khi formatter chạy

Nếu formatter tự động đặt ngoặc hoặc ngắt dòng theo quy tắc của nó, việc liên tục chỉnh tay để ép một phong cách khác thường dẫn tới vòng lặp:

```text
Lập trình viên sửa tay
        |
        v
CI chạy formatter và báo khác biệt
        |
        v
Lập trình viên sửa lại
        |
        v
Reviewer đề nghị sửa về kiểu cá nhân
        |
        +----> Lặp lại
```

Cách giải quyết không phải yêu cầu mọi người nhớ một ngoại lệ ngầm. Hãy chọn cấu hình thống nhất hoặc chấp nhận kết quả formatter trong phạm vi đã thống nhất. Ngoại lệ thực sự cần có cơ chế chính thức và lý do cụ thể, không tùy ý từng pull request.

## 5. Ba lớp quy ước thường cần trong một dự án

Một dự án Java có thể cần kiểm soát ba lớp khác nhau.

### Lớp 1: quy tắc của tệp văn bản

Các quy ước như UTF-8, ký tự xuống dòng, dòng cuối tệp, khoảng trắng thừa. Công cụ như EditorConfig giúp nhiều editor thống nhất **những thuộc tính được editor/plugin hỗ trợ**.

Ví dụ tệp `.editorconfig` mang tính minh họa:

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.java]
indent_style = space
indent_size = 4

[*.md]
trim_trailing_whitespace = false
```

Một số tệp Markdown dùng hai dấu cách cuối dòng làm ký hiệu xuống dòng; vì vậy cấu hình có thể chủ động giữ khoảng trắng cuối dòng trong Markdown. Đây là quyết định theo định dạng tệp, không phải một quy tắc tuyệt đối.

EditorConfig **không thay thế** Java formatter. Nó không tự quyết định đầy đủ việc ngắt biểu thức Java, sắp xếp import hoặc bố trí mọi dấu ngoặc. Một số cài đặt có thể bị formatter hoặc IDE ưu tiên khác đi; nhóm nên thử kết quả thực tế.

### Lớp 2: định dạng cú pháp Java

Một formatter Java, chẳng hạn `google-java-format` hoặc cơ chế format được nhóm chọn trong IDE, có thể tự động viết lại hình thức mã theo các quy tắc cụ thể.

Khi chọn công cụ, nên đánh giá:

- Có hỗ trợ phiên bản Java và cú pháp hiện dự án dùng không?
- Có thể chạy từ command line hoặc build để CI kiểm tra không?
- Có thể chốt **phiên bản** công cụ thay vì để mỗi máy chọn một bản khác nhau không?
- Có thể áp dụng trong IDE để người phát triển thấy kết quả trước khi commit không?
- Có cách quy định phạm vi file nguồn và ngoại lệ hợp lý không?

### Lớp 3: quy ước vượt quá định dạng

Các quy tắc về tên package, tên hằng, Javadoc hoặc những điều cấm sử dụng có thể được kiểm tra bằng Checkstyle hoặc công cụ khác, nếu phù hợp. Static analysis và test tiếp tục bảo vệ lỗi lập trình và hành vi nghiệp vụ.

Không nên cấu hình hai công cụ cùng sửa một khía cạnh nhưng cho **kết quả đối nghịch**. Ví dụ IDE tự định dạng một kiểu, plugin build lại yêu cầu kiểu khác sẽ khiến người phát triển liên tục chạy format qua lại.

## 6. Quy trình tối thiểu: một nguồn quy tắc, hai điểm thực thi

Một quy trình dễ duy trì có thể trông như sau:

```text
Nhóm chọn formatter và chốt phiên bản/cấu hình
                     |
                     v
         Repository giữ quy ước
                     |
         +-----------+-------------+
         |                         |
         v                         v
 Máy lập trình viên              CI / build
 Format trước commit             Kiểm tra format
         |                         |
         +-----------+-------------+
                     |
                     v
             Pull request
                     |
                     v
      Review logic, thiết kế, test
```

**Local:** người viết có cách chủ động chạy formatter, có thể tích hợp trong IDE hoặc command build. Không nhất thiết ép format toàn repository mỗi khi lưu một file.

**CI:** kiểm tra mã đang trong pull request có tuân theo quy ước không. CI nên báo lỗi có hướng dẫn chạy công cụ, không âm thầm thay đổi file trong một job kiểm tra rồi bỏ kết quả.

**Review:** phần thảo luận về dấu cách và ngoặc nên được chuyển về kết quả công cụ. Reviewer vẫn xử lý những trường hợp thay đổi định dạng vô tình làm khó đọc một biểu thức phức tạp bằng cách xem có cần chia nhỏ biểu thức theo **ý nghĩa** hay không.

### Vì sao cần chốt phiên bản?

Hai phiên bản formatter có thể khác nhau về cách xử lý cú pháp mới, import hoặc ngắt dòng. Nếu mỗi thành viên dùng một phiên bản cài riêng trên máy, cùng một file có thể bị format lại mỗi lần đổi người sửa.

Muốn có kết quả lặp lại, tối thiểu phải thống nhất:

- Công cụ và phiên bản.
- Quy tắc hoặc profile được chọn (nếu công cụ có nhiều profile).
- Phạm vi file được định dạng.
- Cách chạy từ build và CI.
- Cách xử lý những ngoại lệ được chấp thuận.

Khi nâng phiên bản formatter, coi đó là **thay đổi quy ước có kiểm soát**, có thể tạo diff định dạng riêng.

## 7. Minh họa tích hợp formatter trong Gradle

Ví dụ sau dùng một plugin formatter thường gặp trong hệ sinh thái Gradle: **Spotless** kết hợp với `google-java-format`. Đây là cấu hình **minh họa cho Gradle Groovy DSL**, không khẳng định repository đang dùng plugin hay phiên bản cụ thể.

```groovy
plugins {
    id 'java'
    id 'com.diffplug.spotless' version '<approved-plugin-version>'
}

spotless {
    java {
        target 'src/**/*.java'
        googleJavaFormat('<approved-formatter-version>')
    }
}
```

Các chuỗi `<approved-plugin-version>` và `<approved-formatter-version>` là **chỗ thay thế**, cần điền các phiên bản thực đã được dự án kiểm tra tương thích trước khi chạy. Chúng không phải cấu hình có thể sao chép nguyên xi vào build sản xuất.

Với cấu hình tương ứng, quy trình thường là:

```text
# Máy Windows/PowerShell tại thư mục dự án:
.\gradlew.bat spotlessApply
.\gradlew.bat spotlessCheck

# Máy macOS/Linux:
./gradlew spotlessApply
./gradlew spotlessCheck
```

- `spotlessApply`: áp dụng định dạng cho file nằm trong phạm vi cấu hình.
- `spotlessCheck`: kiểm tra xem file có đúng format dự kiến không; không nhằm thay đổi file nguồn.
- Có thể thêm bước check vào pipeline CI để bảo đảm mã đưa vào nhánh chính thống nhất.

Tên task trên là ví dụ theo cách Spotless Gradle plugin cung cấp. Cấu hình, dependency, phiên bản và tác vụ thực tế phải được xác minh theo công cụ mà dự án sử dụng. **Không chạy thêm formatter khác chỉ vì ví dụ này** nếu repository đã có quy ước riêng.

### Phạm vi file là một phần quan trọng của cấu hình

Định dạng mọi file `*.java` có thể vô tình chạm mã được sinh tự động hoặc thư viện chép vào repository. Cần xem phạm vi nào là mã do nhóm sở hữu, tệp nào do generator tạo và tệp nào thuộc bên thứ ba.

Quy tắc thường hợp lý:

- **Mã nguồn do nhóm sở hữu:** áp dụng formatter chung.
- **Mã được sinh lại bằng công cụ:** ưu tiên cấu hình generator; tránh chỉnh file đầu ra thủ công.
- **Mã vendor/bên ngoài:** không tự ý format nếu việc thay đổi làm mất khả năng cập nhật hay đối chiếu nguồn.
- **Tệp có cú pháp đặc biệt hoặc cấu trúc nhúng:** đánh giá formatter có hỗ trợ đúng không trước khi đưa vào phạm vi.

Không nên tạo một danh sách ngoại lệ quá rộng chỉ để “cho CI xanh”. Mỗi ngoại lệ cần có lý do và người bảo trì hiểu rõ.

## 8. IDE và CI phải cùng đưa ra một câu trả lời

Một nhóm có thể dùng IntelliJ IDEA, Eclipse, VS Code hoặc trình soạn thảo khác. Việc mỗi người dùng IDE khác nhau không buộc cả nhóm phải thay đổi công cụ yêu thích, nhưng **đầu ra định dạng trong repository phải nhất quán**.

Có ba cách phối hợp thường gặp:

1. Dùng tích hợp formatter tương ứng trong IDE để định dạng ngay tại nơi viết.
2. Dùng lệnh build chung làm nguồn sự thật và chạy khi chuẩn bị commit.
3. Kết hợp cả hai: IDE chạy nhanh, CI xác nhận cuối cùng bằng cùng phiên bản/cấu hình.

Nguy cơ hay gặp là IDE dùng bộ format riêng, còn CI dùng một bộ khác. Khi đó người viết format trong IDE xong vẫn bị CI báo lỗi, dù không sửa logic.

Cách kiểm chứng đơn giản: chuẩn bị cùng một file mẫu có phương thức dài, import và biểu thức lồng nhau; format bằng IDE rồi chạy lệnh check trong build. Nếu check báo khác biệt, phải đồng bộ công cụ hoặc ngừng coi nút “Reformat Code” mặc định của IDE là nguồn quy ước của dự án.

**Đừng yêu cầu lập trình viên tự đoán formatter nào “đúng hơn”.** Repository và pipeline cần có một nguồn quy tắc đã thống nhất.

## 9. Tự động format lúc nào là phù hợp?

Có nhiều điểm kích hoạt:

| Thời điểm | Lợi ích | Rủi ro/cần cân nhắc |
| --- | --- | --- |
| Khi lưu file | Phản hồi rất sớm, gần như không tốn công nhớ | Có thể làm thay đổi lớn ngoài ý muốn khi mở file cũ |
| Trước commit | Có cơ hội kiểm tra diff trước khi ghi commit | Hook quá chậm hoặc tự sửa nhiều file có thể gây khó chịu |
| Chạy lệnh theo yêu cầu | Chủ động kiểm soát phạm vi thay đổi | Dễ quên nếu CI không kiểm tra |
| Trong CI ở chế độ check | Mọi nhánh được kiểm tra như nhau | Không tự sửa file local; cần báo cách khắc phục |
| Trong job tự sửa PR | Giảm thao tác thủ công | Phải quản lý quyền ghi, commit sinh tự động và tránh vòng lặp pipeline |

Với bài học này, cách mặc định dễ lý giải là **cho developer chạy format khi viết; để CI chỉ kiểm tra**. Nếu nhóm dùng bot tự format PR, cần thống nhất quyền, cách hiển thị diff và trách nhiệm review; không nên tạo commit thay đổi từ nguồn không rõ.

Đặc biệt cẩn thận với hook chạy trên **toàn repository** khi mỗi commit chỉ sửa vài dòng. Nó có thể làm một commit nghiệp vụ vô tình đổi hàng nghìn dòng chỉ vì plugin hoặc cấu hình trên máy khác phiên bản.

## 10. Vì sao format tự động làm code review tốt hơn?

Một pull request chứa hai loại thay đổi:

- **Thay đổi ngữ nghĩa:** điều kiện, thuật toán, trạng thái, quyền, exception, dữ liệu lưu trữ.
- **Thay đổi trình bày:** khoảng trắng, thụt lề, vị trí ngoặc, import sắp xếp lại.

Khi chúng trộn vào nhau, reviewer phải tách bằng mắt trước khi hiểu logic.

Ví dụ phần code cần sửa chỉ là:

```java
// Trước:
if (subtotalVnd > FREE_SHIPPING_THRESHOLD_VND) {
    return 0L;
}

// Sau:
if (subtotalVnd >= FREE_SHIPPING_THRESHOLD_VND) {
    return 0L;
}
```

Điểm quan trọng nhất là thay `>` thành `>=`, nghĩa là **đơn đúng bằng ngưỡng** giờ được miễn phí. Nếu cùng commit còn thay hàng trăm dòng định dạng xung quanh, thay đổi biên này có thể bị bỏ qua.

Dùng formatter giúp file dần hội tụ về một cách trình bày. Nhưng khi đưa formatter vào hệ thống cũ, cần chiến lược riêng để tránh tạo nhiễu lớn trong pull request tính năng.

### Review không nên lặp lại công việc của CI

Nếu `spotlessCheck` đã xác nhận quy ước, reviewer không cần bình luận từng dấu cách. Review có thể tập trung vào:

- Mã có diễn đạt đúng yêu cầu không?
- Xử lý đầu vào sai và ngoại lệ có hợp lý không?
- Tên biến/hàm có bộc lộ ý định không?
- Có nguy cơ lộ dữ liệu, cạn tài nguyên hoặc tạo trạng thái không nhất quán không?
- Test có bảo vệ các ranh giới cần thiết không?

Nếu một quy tắc hình thức thường xuyên gây tranh luận nhưng công cụ chưa bắt được, nhóm có thể xem có đáng bổ sung vào formatter/linter không, thay vì lặp cùng bình luận mãi.

## 11. Áp dụng formatter vào repository đã có nhiều mã cũ

Đây là tình huống thường gây tác động lớn nhất. Chạy formatter trên toàn bộ một repository nhiều năm tuổi có thể thay hàng chục nghìn dòng, làm khó review và tạo xung đột với các nhánh tính năng đang mở.

Có hai chiến lược chính.

### Chiến lược A: một thay đổi định dạng riêng, toàn diện

Phù hợp khi repository tương đối nhỏ, nhóm có thể phối hợp thời điểm chuyển đổi và dễ kiểm tra sự tương đương.

Quy trình:

1. Thống nhất công cụ/phiên bản, phạm vi file và cách kiểm tra.
2. Đảm bảo baseline test và build hiện tại đáng tin.
3. Dành một commit hoặc pull request **chỉ format**, không trộn thay đổi logic.
4. Chạy test/check phù hợp và kiểm tra diff để phát hiện những gì không phải format.
5. Merge trong khoảng thời gian phù hợp, thông báo các nhánh đang mở đồng bộ lại.
6. Bật check trong CI để tránh mã mới quay về trạng thái không thống nhất.

Ưu điểm: sau khi hoàn tất, mọi file do nhóm sở hữu có cùng quy tắc. Nhược điểm: diff lớn và nhiều xung đột merge. Việc tách commit làm lịch sử dễ hiểu hơn nhưng không loại bỏ hoàn toàn chi phí phối hợp.

### Chiến lược B: áp dụng dần theo phạm vi được quản lý

Phù hợp với repository lớn hoặc nhiều nhóm đang sửa song song. Có thể bắt đầu từ module mới, thư mục riêng hoặc các file đang được bảo trì, rồi mở rộng dần.

Điều kiện để thành công là **phạm vi kiểm tra phải rõ ràng và nhất quán**, tránh một file bị format lúc có người đụng tới rồi bị đổi ngược bởi cấu hình cũ. Nếu chỉ kiểm tra các file thay đổi trong PR, cần xác định chính xác công cụ và cách chọn phạm vi để không bỏ lọt code mới.

Ưu điểm: diff nhỏ, ít gây xung đột ngay lập tức. Nhược điểm: trong giai đoạn chuyển tiếp, cùng repository có thể tồn tại nhiều phong cách; cần ghi rõ lộ trình hội tụ.

### Đừng “format cho sạch” một vùng mã không liên quan

Giả sử bạn sửa lỗi ở một phương thức 10 dòng, nhưng IDE tự format cả file 2.000 dòng. Pull request trở nên khó đọc và dễ xung đột với nhánh khác.

Nếu repo chưa được format đồng loạt, cân nhắc chỉ format **phạm vi được kế hoạch cho phép** hoặc tách một commit định dạng riêng. Khi formatter hoạt động trên toàn file, việc kiểm soát phạm vi có thể cần xử lý ở cấp file/module chứ không đơn giản là “format đúng mấy dòng”; đừng tin một chế độ chọn dòng sẽ cho kết quả giống với chạy format toàn file.

## 12. Giữ lịch sử Git hữu ích sau khi format hàng loạt

Một thay đổi chỉ về format có thể làm `git blame` trỏ hầu hết dòng về commit định dạng thay vì commit tạo logic ban đầu. Một số quy trình Git hỗ trợ danh sách revision bỏ qua khi blame.

Ví dụ minh họa cách dùng:

```text
# Tệp .git-blame-ignore-revs chứa hash của commit chỉ định dạng:
<format-only-commit-hash>

# Khi cần xem nguồn gốc logic:
git blame --ignore-revs-file .git-blame-ignore-revs path/to/Example.java
```

`<format-only-commit-hash>` là placeholder, không phải hash thực. Việc thêm cấu hình này phải theo chính sách repository và công cụ của nhóm. Nếu commit định dạng có cả chỉnh sửa logic, bỏ qua toàn bộ commit khi blame sẽ che mất nguồn gốc thay đổi thật, vì vậy **phân tách format-only commit có giá trị thực tế**.

Không phải nơi hiển thị Git nào cũng tự dùng cùng thiết lập; cần kiểm tra tích hợp trong IDE hoặc nền tảng review nếu nhóm dựa vào tính năng này.

## 13. Tính xác định và idempotence của formatter

Hai thuộc tính quan trọng của một công cụ được dùng tự động:

**Tính xác định (*determinism*):** trong điều kiện cùng nội dung, phiên bản và cấu hình, formatter cho cùng một kết quả. Các yếu tố phụ thuộc môi trường cần được cố định khi có thể.

**Tính ổn định khi chạy lại (*idempotence*):** format lần thứ hai không thay đổi kết quả đã được format lần đầu.

Có thể biểu diễn:

\[
F(F(code)) = F(code)
\]

Trong đó `F` là thao tác định dạng với cùng phiên bản và cấu hình. Nếu mỗi lần chạy lại tạo diff mới, phải kiểm tra xung đột cấu hình, các công cụ chạy nối tiếp hoặc lỗi của formatter.

Một kiểm tra thực tế:

```text
1. Format file bằng công cụ chuẩn.
2. Xem diff và xác nhận chỉ thay đổi hợp lệ.
3. Chạy format lại trên chính file đó.
4. Xác nhận lần thứ hai không có thay đổi.
5. Chạy bước check của CI với cùng phiên bản.
```

Không nên coi việc formatter “có chạy” là đủ. CI cần xác nhận repository đã ở trạng thái chuẩn, và nhóm cần biết chính xác lệnh nào giúp sửa khi check thất bại.

### Tránh xung đột giữa nhiều công cụ

Ví dụ:

```text
IDE Formatter A -> chèn dòng trống giữa các nhóm import
Formatter B      -> bỏ dòng trống đó
IDE Formatter A -> chèn lại dòng trống
...
```

Vấn đề không thể giải quyết bằng cách chạy nhiều lần hơn. Hãy chọn nguồn quy tắc cho phần import và tắt hoặc điều chỉnh cơ chế còn lại để không “đánh nhau”.

## 14. Những gì công cụ có thể thay đổi ngoài khoảng trắng

Nhiều formatter không chỉ sửa dấu cách. Tùy công cụ, chúng có thể:

- Ngắt/gộp dòng.
- Chuẩn hóa ngoặc hoặc bố trí toán tử.
- Sắp xếp import hoặc loại bỏ import không dùng.
- Định dạng comment hoặc chú thích theo một số quy tắc.
- Chuẩn hóa xuống dòng và một số đặc điểm file.

Một số tác vụ “auto-fix” của linter hay IDE thậm chí còn thay đổi cú pháp hoặc cấu trúc biểu thức. Vì thế cần phân biệt **formatter bảo toàn ngữ nghĩa theo cam kết của công cụ** với **tác vụ sửa mã tự động** có thể có phạm vi rộng hơn.

Khi áp dụng hoặc nâng phiên bản:

1. Xem diff thực tế, đặc biệt ở file có comment đặc biệt, annotation, text block và import tĩnh.
2. Chạy test/build phù hợp để phát hiện hồi quy.
3. Tránh ghép thay đổi format với cải tiến thuật toán hoặc đổi API trong một commit nếu không cần.
4. Coi các cảnh báo về cú pháp không được hỗ trợ là blocker để chọn phiên bản tương thích.

Mã không thay đổi hành vi ở các test hiện có vẫn chưa chứng minh hoàn toàn tương đương. Tuy nhiên, tách format khỏi logic giúp review có thể kiểm tra thay đổi chính xác hơn.

## 15. Quy ước nào nên để reviewer quyết định?

Sau khi tự động hóa format, vẫn sẽ có những vấn đề đọc mã khó giải quyết bằng quy tắc thuần máy:

### Tên có phù hợp miền nghiệp vụ không?

```java
long calculate(long a, long b) {
    return a + b;
}
```

Formatter không thể suy ra `a` là tiền trước thuế, `b` là phí vận chuyển. Có thể cần:

```java
long calculateTotalVnd(long subtotalVnd, long shippingFeeVnd) {
    return Math.addExact(subtotalVnd, shippingFeeVnd);
}
```

Đây không chỉ là đổi format: nó thay cách diễn đạt hợp đồng và còn thêm hành vi phát hiện tràn số. Mọi thay đổi như vậy cần được review như thay đổi thiết kế/nghiệp vụ, không trộn với việc chuẩn hóa khoảng trắng.

### Một phương thức có làm quá nhiều việc không?

Một phương thức được format đẹp vẫn có thể vừa kiểm tra quyền, tính tiền, gọi dịch vụ ngoài, cập nhật database và gửi email. Tách trách nhiệm cần hiểu bất biến, transaction, thất bại và tác dụng phụ. Formatter không có đủ ngữ cảnh để quyết định.

### Một điều kiện có dễ hiểu không?

Một biểu thức boolean có thể được formatter ngắt nhiều dòng nhưng vẫn khó hiểu. Người viết có thể cần trích ra hàm tên rõ, thay magic number bằng enum hoặc dùng kiểu miền thích hợp. Đây là **refactor nhằm giảm độ phức tạp nhận thức**.

### Khi nào cần ngoại lệ?

Đôi khi mã sinh tự động, đoạn nhúng theo định dạng riêng hoặc file được chia sẻ với công cụ bên ngoài không nên chạy formatter chung. Reviewer và người bảo trì cần đánh giá ranh giới đó thay vì tắt kiểm tra tùy ý ở mọi file khó xử lý.

## 16. Dùng formatter để hỗ trợ onboarding và làm việc đa nhóm

Một người mới tham gia dự án phải học nhiều thứ: kiến trúc, dữ liệu, API, quy tắc lỗi và cách deploy. Nếu còn phải nhớ hàng chục quy ước về dấu cách, import và line wrapping, chi phí nhập môn tăng thêm mà không tạo giá trị nghiệp vụ.

Khi formatter là một phần của build:

- Người mới có thể chạy một lệnh rõ ràng để đưa file về quy ước.
- Quy tắc không phụ thuộc việc ai là reviewer.
- Người dùng IDE khác nhau vẫn có cơ chế xác minh chung.
- Tài liệu code review có thể tập trung vào câu hỏi về hành vi và chất lượng thực.
- Các chỉnh sửa nhỏ ít bị trộn với thay đổi format do sở thích cá nhân.

Công cụ **không xóa nhu cầu học quy ước**; nó biến phần cơ học thành phản hồi cụ thể. Khi check lỗi, thông báo nên đưa ra đường dẫn file, vị trí hoặc diff hữu ích và lệnh sửa phù hợp.

Một quy ước nhất quán cũng làm việc tìm kiếm/thay thế và đọc lịch sử mã dễ hơn. Tuy nhiên, nó không bảo đảm tên đặt đúng, ví dụ thiết kế tốt hoặc test đầy đủ.

## 17. Kiểm chứng quy trình bằng một thay đổi nhỏ

Trước khi bật check cho toàn repository, hãy thử trên một tập file Java đại diện:

- Một file có nhiều import.
- Một phương thức có tham số và biểu thức dài.
- Một file có comment/Javadoc.
- Một file dùng cú pháp phiên bản Java hiện tại, như `record` hoặc `switch` expression nếu dự án hỗ trợ.
- Một file có newline/encoding theo quy ước.
- Một file không nên được formatter chạm vào, ví dụ mã sinh tự động.

Thử theo chuỗi:

```text
A. Cùng một commit và cùng cấu hình.
B. Chạy format trên máy của developer.
C. Chạy format lần hai: không phát sinh diff.
D. Chạy bước check trong build: PASS.
E. Chạy cùng check trên CI: PASS.
F. Thử đưa một file định dạng sai:
   CI phải FAIL và chỉ dẫn cách sửa.
G. Sửa bằng công cụ chuẩn:
   CI trở về PASS.
```

Trong một dự án Java, cũng nên xác nhận source vẫn biên dịch và các test cần thiết qua sau thao tác format. Nếu formatter được nâng phiên bản, lặp lại phép thử này để nhận diện thay đổi đầu ra.

### Ma trận vấn đề thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Format trên IDE xong CI vẫn lỗi | Hai formatter hoặc version khác nhau | Đồng bộ phiên bản, plugin và lệnh chuẩn |
| Cùng file bị format lại mỗi lần save | Cấu hình format và import organizer xung đột | Chọn một nguồn quy tắc cho vùng chồng lấn |
| PR chỉ đổi logic một dòng nhưng diff rất lớn | Chạm file cũ chưa format hoặc chạy format cả repo | Tách commit định dạng, lên kế hoạch chuyển đổi |
| CI không phát hiện file sai format | Chưa bao phủ đúng source set/path | Xem target include/exclude và task check |
| File generated liên tục bị sửa | Formatter chạm đầu ra generator | Chọn phạm vi phù hợp hoặc cấu hình generator |
| Tool báo không hiểu cú pháp Java | Formatter/version không tương thích | Chọn phiên bản hỗ trợ ngôn ngữ dự án |
| Reviewer vẫn tranh luận dấu cách | Chưa thống nhất dùng công cụ làm chuẩn | Ghi quy ước review và đường dẫn lệnh check |
| Tắt check để PR qua | Thiếu cách sửa hoặc rule không hợp lý | Cải thiện công cụ/quy định, không mở ngoại lệ tùy tiện |

## 18. Các sai lầm hay gặp

**“Có formatter thì mã chắc chắn sạch.”** Formatter không biết mọi quy tắc nghiệp vụ hay độ phức tạp thiết kế. Nó giải quyết cách trình bày, không thay thế review và test.

**“Mỗi người tự format theo IDE mình là được.”** Cùng file có thể đổi qua đổi lại giữa các IDE. Cần một công cụ và cấu hình được xem là chuẩn trong repo.

**“Không cần chốt phiên bản.”** Một bản nâng cấp formatter có thể đổi output dù mã nguồn không đổi. Nên pin version khi công cụ hỗ trợ.

**“Cứ bật format toàn bộ ngay trong PR tính năng.”** Điều này tạo diff lớn khó review và xung đột không cần thiết. Cần kế hoạch đưa formatter vào mã cũ.

**“CI nên âm thầm sửa file để build xanh.”** Việc tự sửa nhưng không phản ánh lại commit của developer có thể gây lệch giữa thứ đã review và thứ được kiểm tra. Với job check, nên báo sai khác và cách sửa.

**“Formatter và linter là một.”** Formatter chủ yếu tạo output chuẩn; linter có thể kiểm tra quy tắc mà formatter không thể tự quyết định. Cần biết công cụ đang chịu trách nhiệm điều gì.

**“Mọi ngoại lệ nên được bỏ qua vì file khó format.”** Loại trừ tùy tiện phá tính nhất quán. Chỉ giữ ngoại lệ khi có nguyên nhân kỹ thuật hoặc quyền sở hữu rõ ràng.

**“Định dạng là thứ quan trọng nhất trong review.”** Một thay đổi dấu so sánh, cách xử lý null hoặc ranh giới transaction có thể quan trọng hơn toàn bộ khoảng trắng trong diff.

## 19. Bài tập tình huống

### Tình huống A: hai IDE định dạng khác nhau

Nhóm có lập trình viên dùng IntelliJ và VS Code. Cả hai đều bật format-on-save, nhưng CI chạy một formatter Java riêng. Cùng file liên tục thay đổi phần import và ngắt dòng.

Hãy xác định nguồn không nhất quán, đề xuất **một nguồn quy tắc** và mô tả phép thử để xác nhận IDE/CI cho kết quả tương thích. Có cần bắt tất cả đổi IDE không?

### Tình huống B: đưa formatter vào mã cũ

Repository có hàng nghìn file Java; nhiều nhánh tính năng đang mở. Một thành viên chạy formatter trên toàn bộ rồi đưa vào PR sửa lỗi nhỏ, tạo diff 30.000 dòng.

Bạn sẽ xử lý PR này thế nào để vẫn giữ khả năng review? Khi nào nên chọn format-only commit, khi nào áp dụng dần? Cần truyền đạt gì cho các nhánh đang phát triển?

### Tình huống C: mã được sinh tự động

Một thư mục Java được sinh từ schema mỗi lần build. Formatter của nhóm thay cách xuống dòng trong đầu ra, nhưng lần build kế tiếp generator lại tạo kiểu cũ.

Hãy xác định vì sao format trực tiếp vào file được sinh không giải quyết tận gốc. Bạn sẽ cấu hình generator, phạm vi formatter hay lộ trình xử lý như thế nào?

### Tình huống D: CI báo lỗi nhưng developer không biết sửa

Một pull request thất bại với thông báo duy nhất “format check failed”. Người viết thử thêm dấu cách thủ công nhưng mỗi lần đều sai ở chỗ khác.

Hãy đề xuất thông báo CI tốt hơn và hướng dẫn chạy lệnh format/check chung. Nếu plugin trên máy không cài được, nhóm cần cung cấp cơ chế nào để phát triển không bị lệ thuộc vào cấu hình IDE cá nhân?

### Tình huống E: formatter mới tạo diff lớn

Nhóm nâng phiên bản formatter, CI bắt đầu báo sai format ở nhiều file dù không ai sửa logic. Một người muốn chạy `formatApply` rồi trộn toàn bộ vào PR nâng dependency có thay đổi hành vi.

Hãy đề xuất cách tách commit, kiểm tra diff, xác nhận test và giữ lịch sử blame hữu ích. Vì sao nên ghi quyết định nâng phiên bản trong PR riêng?

### Tình huống F: tranh luận vẫn chưa biến mất

Formatter đã thống nhất mọi khoảng trắng, nhưng reviewer tiếp tục bàn cãi liệu một class có nên tách interface, đặt tên `process` hay `calculateShippingFee`, hoặc nên bắt exception ở đâu.

Hãy phân loại những vấn đề mà formatter có thể giải quyết và những vấn đề đòi hỏi hiểu ngữ cảnh. Có thể tự động hóa phần nào bằng linter không, và phần nào vẫn cần review thiết kế?

Với mỗi tình huống, hãy nêu: **triệu chứng → quy tắc có thể tự động hóa → phạm vi và công cụ → cách xác minh → việc còn cần con người quyết định**.

## 20. Ghi nhớ

**Dùng công cụ định dạng để giảm tranh luận thủ công** không có nghĩa là ngừng quan tâm đến cách trình bày. Nó là cách biến những quy tắc cơ học lặp lại thành một **hợp đồng nhất quán, có thể kiểm tra và thực hiện bằng máy**.

- Chọn formatter phù hợp với ngôn ngữ và repository; chốt phiên bản/cấu hình khi có thể.
- Phân biệt formatter với quy ước đặt tên, linter, static analysis và kiểm thử.
- Dùng EditorConfig hoặc cơ chế tương đương cho thuộc tính tệp cơ bản; đừng mặc định nó định dạng toàn bộ cú pháp Java.
- Cho người viết mã một lệnh format rõ ràng và để CI kiểm tra cùng quy tắc.
- Giữ phạm vi file minh bạch; xử lý mã cũ và mã sinh tự động theo kế hoạch, tránh diff ngoài ý muốn.
- Kiểm chứng formatter chạy lại không tạo thêm diff và IDE/CI thống nhất đầu ra.
- Chuyển review khỏi tranh luận dấu cách để tập trung vào tính đúng, rủi ro, khả năng đọc, test và khả năng thay đổi.

Một nhóm hiệu quả không nhất thiết có cùng sở thích định dạng; họ có thể **đồng ý giao việc đó cho công cụ** và dành thời gian cho những quyết định mà công cụ chưa đủ ngữ cảnh để đưa ra.
