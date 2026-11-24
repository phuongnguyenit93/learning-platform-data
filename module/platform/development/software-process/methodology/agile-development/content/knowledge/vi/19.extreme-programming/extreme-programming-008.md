# Tái cấu trúc liên tục để bảo toàn khả năng thay đổi

Một nhóm phát triển nền tảng học trực tuyến bắt đầu bằng yêu cầu nhỏ: **người học mở lại video tại vị trí đã dừng**. Vài Sprint sau, sản phẩm cần hỗ trợ nhiều thiết bị, mất mạng, thay đổi quy tắc lưu tiến độ và phân quyền theo khóa học. Nếu logic cũ bị sao chép vào nhiều controller, điều kiện lồng nhau khó hiểu và kiểm thử không đủ tin cậy, mỗi yêu cầu mới sẽ mất nhiều công sức hơn yêu cầu trước.

Nhóm có thể lựa chọn “cứ thêm nhánh điều kiện cho kịp Sprint” rồi dành một tháng về sau để viết lại hệ thống. Nhưng trong thời gian chờ, các thay đổi tiếp tục làm cấu trúc rối hơn. **Extreme Programming (XP)** đề xuất cách khác: thường xuyên **tái cấu trúc (refactoring)** những phần mã đang được thay đổi, giữ thiết kế đơn giản và được bảo vệ bằng kiểm thử, để khả năng thay đổi không bị bào mòn theo thời gian.

Điều quan trọng nhất: **refactoring là thay đổi cấu trúc bên trong mà không cố ý thay đổi hành vi có thể quan sát từ bên ngoài**. Nó không phải tên gọi chung cho mọi công việc “dọn code”, không thay thế kiểm thử, và không cho phép sửa nghiệp vụ tùy ý trong lúc đổi cấu trúc.

Bài thuộc chương **Extreme Programming** của module **AGILE_DEVELOPMENT**, nơi Agile hướng đến phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. Tái cấu trúc liên tục hỗ trợ user story, backlog, Scrum, Kanban và các thực hành XP bằng cách giúp nhóm tiếp tục tạo ra các lát chức năng nhỏ mà không phải trả chi phí tích hợp, sửa lỗi và thay đổi ngày càng cao.

Sau khi học, bạn có thể:

1. Giải thích refactoring, phân biệt nó với thêm tính năng, sửa lỗi, tối ưu hiệu năng và viết lại hệ thống.
2. Nêu lý do refactoring là hoạt động **thường xuyên, có mục đích** trong XP, không chỉ là một “giai đoạn dọn code” cuối dự án.
3. Thực hiện những phép tái cấu trúc nhỏ, có khả năng kiểm chứng, bằng kiểm thử và tích hợp liên tục.
4. Nhận diện **code smells** và chọn kỹ thuật phù hợp thay vì sửa theo sở thích cá nhân.
5. Tái cấu trúc mã Java từng bước, giữ nguyên đầu ra và các trường hợp biên qua ví dụ kiểm thử JUnit.
6. Xử lý mã cũ ít kiểm thử, phụ thuộc bên ngoài, rủi ro dữ liệu, API, bảo mật và đồng thời.
7. Đưa refactoring vào nhịp làm việc Scrum/Kanban mà vẫn minh bạch về giá trị và Definition of Done.
8. Đánh giá kết quả bằng khả năng thay đổi, thời gian luồng và chất lượng, không chỉ bằng số dòng mã đã xóa.

## 1. Refactoring là gì?

**Refactoring** là thay đổi thiết kế hoặc cấu trúc bên trong phần mềm, thông qua những bước có kiểm soát, trong khi **bảo toàn hành vi bên ngoài mà người sử dụng hoặc hệ thống tích hợp đang dựa vào**.

Các thay đổi thường thấy:

- Đổi tên hàm hoặc biến để diễn đạt đúng ý nghĩa.
- Tách một phương thức dài thành những phương thức nhỏ có mục đích rõ.
- Loại bỏ logic trùng lặp và gom một quy tắc nghiệp vụ vào đúng nơi quản lý.
- Đưa trách nhiệm về đúng lớp hoặc module.
- Thay các điều kiện phân nhánh khó quản lý bằng cấu trúc đơn giản hơn khi phù hợp.
- Giảm phụ thuộc vòng tròn, làm rõ ranh giới giữa logic nghiệp vụ và I/O.
- Cải thiện khả năng kiểm thử mà không thay đổi kết quả người dùng đang nhận.

**Mục đích không phải tạo ra nhiều lớp hơn hoặc làm code trông “đẹp” theo gu cá nhân.** Mục đích là giảm chi phí hiểu, kiểm tra và thay đổi phần mềm ở những nơi có nhu cầu thực.

### 1.1. “Không thay đổi hành vi” cụ thể là gì?

Hành vi có thể quan sát không chỉ là giá trị trả về của một phương thức. Tùy phạm vi và hợp đồng hệ thống, nó có thể gồm:

| Loại hành vi | Ví dụ cần giữ khi refactor |
| --- | --- |
| **Đầu ra nghiệp vụ** | Vị trí video được khôi phục đúng, mã lỗi/điều kiện áp dụng không đổi. |
| **Tác dụng phụ** | Có/không ghi dữ liệu, phát sự kiện hay gửi thông báo theo cùng quy tắc. |
| **Quyền truy cập** | Người học không đọc được tiến độ của tài khoản khác. |
| **Hợp đồng API** | Định dạng phản hồi, trạng thái HTTP, trường dữ liệu và tương thích khách hàng. |
| **Dữ liệu lưu trữ** | Giá trị tồn tại, quy tắc giao dịch và ý nghĩa trạng thái không bị thay đổi ngoài dự kiến. |
| **Trường hợp biên** | Dữ liệu rỗng, âm, sát ngưỡng, lỗi hoặc timeout được xử lý như cam kết. |
| **Yêu cầu phi chức năng quan trọng** | Giới hạn hiệu năng, khả năng chịu tải, tính đồng thời và an toàn vẫn đáp ứng ràng buộc. |

Đôi khi cấu trúc cũ có một **lỗi thực sự**. Trong refactoring thuần túy, nhóm cần nhận diện lỗi đó và **tách việc sửa hành vi thành thay đổi riêng** để xem xét, kiểm thử và giải thích rõ. Không nên âm thầm sửa nghiệp vụ trong một pull request tự mô tả là “chỉ dọn code”.

### 1.2. Phân biệt các loại thay đổi

| Loại công việc | Mục tiêu | Hành vi bên ngoài có dự định đổi không? |
| --- | --- | --- |
| **Refactoring** | Cải thiện cấu trúc và khả năng thay đổi. | **Không**. |
| **Thêm tính năng** | Cung cấp khả năng mới cho người dùng/hệ thống. | **Có**. |
| **Sửa lỗi (bug fix)** | Chỉnh một hành vi đang sai so với kỳ vọng hợp lệ. | **Có**, ở trường hợp bị lỗi. |
| **Tối ưu hiệu năng** | Cải thiện tốc độ/tài nguyên theo tiêu chí đo. | Hành vi chức năng thường được giữ; đặc tính vận hành **cố ý thay đổi**. |
| **Viết lại hệ thống (rewrite)** | Thay phần triển khai lớn bằng cấu trúc mới. | Có thể muốn giữ hành vi, nhưng phạm vi và rủi ro lớn hơn rất nhiều. |
| **Nâng cấp API hoặc lược đồ dữ liệu** | Thay hợp đồng, mô hình dữ liệu hoặc nền tảng. | Có thể có thay đổi tương thích; không tự động là refactoring thuần túy. |

Trong thực tế, một nỗ lực cải tiến có thể kết hợp nhiều loại công việc. Điều cần làm là **tách và ghi rõ loại thay đổi, kết quả mong đợi và biện pháp kiểm chứng**.

## 2. Vì sao phải tái cấu trúc liên tục?

Trong sản phẩm còn phát triển, yêu cầu liên tục xuất hiện và hiểu biết của nhóm về miền nghiệp vụ liên tục thay đổi. Một thiết kế hợp lý cho ba trường hợp hôm nay có thể thành gánh nặng khi phải hỗ trợ mười trường hợp ngày mai.

Nếu chỉ thêm tính năng:

1. Logic tương tự xuất hiện ở nhiều nơi.
2. Điều kiện nghiệp vụ mới được chèn vào những phương thức vốn đã dài.
3. Các module phụ thuộc nhau theo những hướng khó nhìn.
4. Mỗi sửa đổi cần đọc nhiều code, kiểm tra nhiều trường hợp và phối hợp nhiều người.
5. Nhóm ngại đụng vào khu vực phức tạp, nên lại thêm một lớp xử lý tạm.
6. Khả năng thay đổi tiếp tục giảm.

Refactoring phá vòng lặp đó **trước khi nó trở thành dự án tái thiết quy mô lớn**.

~~~mermaid
flowchart TD
    A["Có user story hoặc thay đổi mới"] --> B["Hiểu code và điều kiện chất lượng"]
    B --> C{"Cấu trúc hiện tại có cản trở thay đổi?"}
    C -->|"Không đáng kể"| D["Thực hiện lát giá trị nhỏ"]
    C -->|"Có"| E["Bổ sung / kiểm tra lưới an toàn hành vi"]
    E --> F["Refactor nhỏ, không đổi hành vi"]
    F --> G["Chạy kiểm thử và tích hợp"]
    G --> H{"Hành vi và ràng buộc còn đúng?"}
    H -->|"Không"| I["Hoàn tác / sửa bước vừa làm"]
    I --> E
    H -->|"Có"| D
    D --> J["Đạt DoD, thu phản hồi"]
    J --> K["Học về nhu cầu tiếp theo"]
    K --> A
~~~

Sơ đồ nhấn mạnh **refactoring là một phần dòng phát triển liên tục**, không phải cổng bắt buộc phải làm trước mọi thay đổi. Khi code đã đơn giản và an toàn, không cần “tái cấu trúc cho có”.

### 2.1. Khả năng thay đổi là tài sản của sản phẩm

Khả năng thay đổi tốt giúp nhóm:

- Thêm một quy tắc nghiệp vụ mà không phải sửa hàng chục chỗ.
- Hiểu và kiểm thử tác động trong phạm vi nhỏ.
- Tích hợp liên tục mà ít xung đột.
- Sửa lỗi nhanh hơn và hạn chế hồi quy.
- Đưa người mới vào phần code rõ trách nhiệm hơn.
- Chọn thay đổi theo phản hồi người dùng, thay vì né yêu cầu vì code quá rối.

Đây là giá trị **gián tiếp nhưng có thực**: refactoring không nhất thiết tạo màn hình mới hôm nay; nó giúp giữ năng lực giao giá trị trong những lần thay đổi tiếp theo.

### 2.2. Không phải mọi đoạn code đều đáng refactor ngay

Một mô-đun ổn định, ít thay đổi và không gây rủi ro có thể chưa cần đầu tư lớn. Ngược lại, một đoạn được sửa trong hầu hết các Sprint, thường gây lỗi hoặc buộc nhóm né việc mới có thể là điểm ưu tiên cao.

Chọn nơi refactor dựa trên **tần suất thay đổi, mức khó hiểu, chi phí lỗi, phụ thuộc, rủi ro và giá trị của công việc sắp tới**, không chỉ dựa vào số dòng hoặc độ dài tên lớp.

## 3. Năm giá trị XP tạo môi trường cho refactoring

XP gắn với những giá trị nền tảng: **communication (giao tiếp), simplicity (đơn giản), feedback (phản hồi), courage (can đảm) và respect (tôn trọng)**.

| Giá trị XP | Liên hệ với tái cấu trúc liên tục |
| --- | --- |
| **Giao tiếp** | Developers thảo luận ý nghĩa nghiệp vụ và trách nhiệm code; không refactor theo giả định riêng khi hợp đồng còn mơ hồ. |
| **Đơn giản** | Giữ thiết kế đủ cho nhu cầu hiện tại, không xây tầng trừu tượng phức tạp cho những khả năng chưa được xác minh. |
| **Phản hồi** | Kiểm thử, CI, review và người dùng nhanh chóng cho biết thay đổi có an toàn và hữu ích không. |
| **Can đảm** | Dám cải thiện cấu trúc xấu, dám nêu rủi ro và hoàn tác khi bước refactor không còn an toàn. |
| **Tôn trọng** | Không đổ lỗi cho tác giả code cũ; cộng tác để duy trì khả năng bảo trì cho người sẽ làm tiếp. |

Trong XP, refactoring thường kết hợp với **TDD, pair programming, continuous integration, collective code ownership, coding standards, simple design và sustainable pace**. Những thực hành này hỗ trợ lẫn nhau:

- Kiểm thử tốt làm refactor ít rủi ro hơn.
- Refactoring làm viết kiểm thử và thay đổi tiếp theo dễ hơn.
- CI giúp nhận ra hồi quy khi thay đổi còn nhỏ.
- Lập trình cặp/review giúp không để một người hiểu toàn bộ thiết kế.
- Thiết kế đơn giản tránh tái cấu trúc thành một kiến trúc dự đoán quá nhiều tương lai.

Không nên biến điều này thành điều kiện phải áp dụng **toàn bộ** thực hành XP trước mới được refactor một phương thức. Chọn các biện pháp an toàn phù hợp, rồi cải thiện dần năng lực của nhóm.

## 4. Red–Green–Refactor: vòng lặp nhỏ và an toàn

Trong **Test-Driven Development (TDD)**, vòng lặp thường được diễn đạt:

1. **Red:** viết một kiểm thử cho hành vi mới, thấy nó thất bại vì chưa có hành vi mong đợi.
2. **Green:** viết mã tối thiểu để kiểm thử mới và các kiểm thử liên quan đạt.
3. **Refactor:** cải thiện cấu trúc **mà không thay đổi hành vi vừa được kiểm chứng**, rồi chạy lại kiểm thử.

~~~mermaid
flowchart LR
    A["Red: test cho hành vi mới"] --> B["Green: triển khai vừa đủ"]
    B --> C["Refactor: cải thiện cấu trúc"]
    C --> D["Chạy test / CI, giữ kết quả"]
    D --> E["Lát hành vi kế tiếp"]
    E --> A
~~~

**Lưu ý quan trọng:** nếu chỉ cải thiện mã đã có mà **không thêm hành vi**, bạn có thể bắt đầu từ **Green**: xác nhận bộ kiểm thử hiện tại đạt, thực hiện một bước refactor, rồi xác nhận vẫn Green. Không phải cố tình tạo kiểm thử thất bại chỉ để gọi hoạt động đó là TDD.

### 4.1. Đơn vị refactor nên nhỏ tới mức nào?

Một bước nhỏ có thể là:

- Đổi tên một biến mơ hồ.
- Tách một biểu thức phức tạp thành tên diễn đạt ý nghĩa.
- Trích xuất một phương thức giữ nguyên tham số và kết quả.
- Di chuyển một quy tắc tới lớp chịu trách nhiệm phù hợp.
- Loại bỏ một nhánh điều kiện trùng, **sau khi chứng minh điều kiện tương đương**.

Sau mỗi bước, chạy bộ kiểm thử nhanh phù hợp và kiểm tra diff. Những kiểm thử tích hợp/contract hoặc đầy đủ hơn có thể chạy ở các điểm bảo vệ khác, nhất là trước merge và khi chạm các ranh giới quan trọng.

### 4.2. Tránh trộn refactor và thay đổi hành vi trong cùng bước

Ví dụ cần sửa hàm tính tiến độ:

- Bước A: thêm kiểm thử nắm bắt các trường hợp hiện tại.
- Bước B: tách phương thức và đổi tên, **giữ nguyên kết quả**.
- Bước C: thêm kiểm thử mô tả quy tắc nghiệp vụ mới.
- Bước D: triển khai quy tắc mới.

Khi một kiểm thử thất bại, nhóm biết nó xảy ra trong **bước đổi cấu trúc** hay **bước đổi nghiệp vụ**. Điều này giảm chi phí tìm lỗi và làm review dễ hơn.

## 5. Nhận diện code smells: tín hiệu để điều tra, không phải bản án

**Code smell** là dấu hiệu cấu trúc có thể gây khó khăn khi hiểu, kiểm thử hoặc sửa đổi. Nó **không tự chứng minh có lỗi** và không bắt buộc mọi lần thấy smell đều phải sửa ngay.

| Code smell | Dấu hiệu | Rủi ro khi thay đổi | Hướng refactor cần cân nhắc |
| --- | --- | --- | --- |
| **Long Method** | Một phương thức xử lý nhiều ý nghĩa và tình huống. | Khó thấy điều kiện quan trọng, khó kiểm thử từng phần. | Extract Method, đặt tên cho điều kiện, giảm mức lồng nhau. |
| **Duplicated Code** | Cùng một quy tắc bị sao chép ở nhiều nơi. | Sửa một chỗ, quên chỗ còn lại. | Gộp quy tắc có ý nghĩa giống nhau vào nơi phù hợp. |
| **Large Class / God Object** | Một lớp biết hoặc làm quá nhiều việc. | Mọi thay đổi đều chạm lớp lớn, phụ thuộc tăng. | Extract Class, tách trách nhiệm theo miền nghiệp vụ. |
| **Feature Envy** | Một phương thức đọc nhiều dữ liệu của đối tượng khác để quyết định. | Logic nằm xa chủ sở hữu dữ liệu/quy tắc. | Move Method hoặc điều chỉnh trách nhiệm. |
| **Long Parameter List** | Hàm có nhiều tham số dễ nhầm thứ tự. | Dễ truyền sai, đổi chữ ký ảnh hưởng nhiều nơi. | Parameter Object khi có ý nghĩa miền rõ. |
| **Primitive Obsession** | Quy tắc miền được biểu diễn bằng chuỗi/số rời rạc. | Giá trị không hợp lệ lọt qua nhiều tầng. | Value Object hoặc kiểu dữ liệu miền có kiểm soát. |
| **Conditional Complexity** | Nhiều điều kiện lồng và trùng lặp. | Thêm trường hợp mới làm tăng nhánh khó đoán. | Guard clauses, Extract Method, chiến lược khi thực sự phù hợp. |
| **Shotgun Surgery** | Một thay đổi nhỏ buộc sửa nhiều file không liên quan trực tiếp. | Rủi ro thiếu chỗ và tăng thời gian review. | Gom quy tắc theo trách nhiệm, giảm coupling. |
| **Divergent Change** | Một lớp bị sửa vì nhiều lý do nghiệp vụ khác nhau. | Khó phân định phạm vi và người hiểu đúng. | Tách trách nhiệm, giảm điểm giao nhau. |
| **Data Clumps** | Một nhóm tham số luôn đi cùng nhau. | Logic xử lý phân tán, dễ không nhất quán. | Tạo đối tượng giá trị hoặc gom dữ liệu có quy tắc. |
| **Speculative Generality** | Tạo nhiều interface/cấu hình cho khả năng chưa dùng. | Tăng độ khó và chi phí đổi. | Xóa trừu tượng không phục vụ nhu cầu, làm đơn giản. |

### 5.1. Smell phải được đặt trong ngữ cảnh

Một phương thức 40 dòng có một luồng xử lý rõ ràng có thể dễ bảo trì hơn một thiết kế chia thành 12 phương thức chỉ gọi qua nhau. Hai đoạn logic nhìn giống nhau nhưng chứa **hai quy tắc nghiệp vụ có lý do thay đổi khác nhau** không nhất thiết nên gộp.

Hãy hỏi: “Nếu yêu cầu mới xuất hiện, phần nào khó thay nhất, vì sao?” rồi chọn refactor giải quyết **khó khăn thực**, không tối ưu chỉ số tĩnh một cách máy móc.

### 5.2. Ưu tiên theo vùng hay thay đổi

Một nguyên tắc hữu ích là cải thiện **vùng code bạn đang làm việc** với phạm vi đủ an toàn. Khi chạm một quy tắc được sao chép ở nhiều nơi, có thể chủ động loại bỏ sự trùng lặp liên quan. Nhưng không cần mở rộng sang mô-đun không liên quan chỉ để đạt một mục tiêu tổng số dòng mã.

## 6. Ví dụ Java: tái cấu trúc quy tắc tiếp tục xem video

Giả sử nhóm có một quy tắc đơn giản để xác định vị trí phát khi người học mở lại video. Ví dụ cố ý giới hạn ở **logic thuần**, chưa bao gồm xác thực thật, I/O hay giao diện, để thấy rõ ý nghĩa của refactoring.

**Quy tắc đang tồn tại:**

- Không có quyền xem video → không phát, trả mã **DENIED**.
- Thời lượng video không hợp lệ (nhỏ hơn hoặc bằng 0) → không phát, **UNAVAILABLE**.
- Chưa lưu tiến độ hoặc giá trị lưu nhỏ hơn/bằng 0 → phát từ đầu, **START**.
- Vị trí đã lưu nằm trong 10 giây cuối hoặc vượt thời lượng theo quy tắc cũ → phát từ đầu, **RESTART**.
- Trường hợp còn lại → phát từ vị trí đã lưu, **RESUME**.

**Quan trọng:** quy tắc “10 giây cuối” có thể cần thảo luận lại với PO trong tương lai, nhưng **refactoring hiện tại phải giữ nguyên** cho tới khi có một thay đổi nghiệp vụ riêng.

### 6.1. Phiên bản ban đầu: điều kiện lồng nhau

Ví dụ Java 17, dùng **record** để biểu diễn quyết định:

~~~java
public final class ResumePolicy {
    public record Decision(
            boolean canPlay,
            int startSecond,
            String reason) {}

    public Decision decide(
            boolean canAccess,
            int durationSeconds,
            Integer savedSecond) {

        if (canAccess) {
            if (durationSeconds > 0) {
                if (savedSecond == null || savedSecond <= 0) {
                    return new Decision(true, 0, "START");
                } else {
                    if (savedSecond >= durationSeconds - 10) {
                        return new Decision(true, 0, "RESTART");
                    } else {
                        return new Decision(true, savedSecond, "RESUME");
                    }
                }
            } else {
                return new Decision(false, 0, "UNAVAILABLE");
            }
        } else {
            return new Decision(false, 0, "DENIED");
        }
    }
}
~~~

Đoạn code có thể chạy đúng trong phạm vi đã nêu, nhưng người đọc phải theo nhiều cấp **if/else** để thấy thứ tự ưu tiên: quyền truy cập → thời lượng → tiến độ → khoảng cuối video. Khi thêm trường hợp mới, phương thức có nguy cơ dài và khó bảo trì hơn.

### 6.2. Bước refactor 1: guard clauses

Giữ nguyên tên lớp, tên phương thức, tham số, record kết quả, mã lý do và thứ tự ưu tiên. Đưa các trường hợp dừng sớm ra đầu:

~~~java
public final class ResumePolicy {
    public record Decision(
            boolean canPlay,
            int startSecond,
            String reason) {}

    public Decision decide(
            boolean canAccess,
            int durationSeconds,
            Integer savedSecond) {

        if (!canAccess) {
            return new Decision(false, 0, "DENIED");
        }
        if (durationSeconds <= 0) {
            return new Decision(false, 0, "UNAVAILABLE");
        }
        if (savedSecond == null || savedSecond <= 0) {
            return new Decision(true, 0, "START");
        }
        if (savedSecond >= durationSeconds - 10) {
            return new Decision(true, 0, "RESTART");
        }
        return new Decision(true, savedSecond, "RESUME");
    }
}
~~~

Đây là một bước **đổi cấu trúc**: làm phẳng điều kiện, không tạo hành vi mới. Sau khi chỉnh, nhóm chạy kiểm thử và xem diff ngay.

### 6.3. Bước refactor 2: đặt tên cho quy tắc

Giả sử quy tắc tiến độ được sử dụng khi thêm tính năng tiếp tục học, nhóm muốn làm rõ ý nghĩa điều kiện:

~~~java
public final class ResumePolicy {
    public record Decision(
            boolean canPlay,
            int startSecond,
            String reason) {}

    public Decision decide(
            boolean canAccess,
            int durationSeconds,
            Integer savedSecond) {

        if (!canAccess) {
            return new Decision(false, 0, "DENIED");
        }
        if (durationSeconds <= 0) {
            return new Decision(false, 0, "UNAVAILABLE");
        }
        if (hasNoSavedProgress(savedSecond)) {
            return new Decision(true, 0, "START");
        }
        if (isNearEnd(savedSecond, durationSeconds)) {
            return new Decision(true, 0, "RESTART");
        }
        return new Decision(true, savedSecond, "RESUME");
    }

    private boolean hasNoSavedProgress(Integer savedSecond) {
        return savedSecond == null || savedSecond <= 0;
    }

    private boolean isNearEnd(int savedSecond, int durationSeconds) {
        return savedSecond >= durationSeconds - 10;
    }
}
~~~

Phiên bản này giữ nguyên **thứ tự điều kiện và biểu thức so sánh**, nhưng ý định được diễn đạt bằng tên hàm. Nó chưa phải thiết kế tốt nhất cho mọi tương lai; đây là cấu trúc đơn giản và có thể kiểm tra hiện nay.

### 6.4. Những thay đổi “nhân tiện” cần tránh

Trong lúc refactor, một người có thể đề xuất:

- Đổi ngưỡng 10 giây thành 15 giây.
- Trừ 5 giây để người học được xem lại ngữ cảnh.
- Trả mã lỗi khác hoặc đổi kiểu giá trị trả về.
- Bắt đầu tự động lưu tiến độ vào database.
- Cho tài khoản chưa đăng nhập phát thử.
- Tự động biến tiến độ vượt thời lượng thành thời lượng tối đa.

Các ý tưởng có thể hợp lý, nhưng đều **có thể thay đổi hành vi hoặc hợp đồng**. Hãy đưa chúng thành thay đổi riêng với acceptance criteria và kiểm thử tương ứng, **không giấu trong commit chỉ có nhãn refactor**.

## 7. Kiểm thử hồi quy cho ví dụ Java

Một lưới an toàn tốt cần kiểm tra **các nhánh và ranh giới** chứ không chỉ một trường hợp thành công.

Ví dụ **JUnit 5** cho phiên bản **ResumePolicy** cuối cùng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ResumePolicyTest {
    private final ResumePolicy policy = new ResumePolicy();

    @Test
    void deniesWhenAccessIsMissing() {
        assertEquals(
                new ResumePolicy.Decision(false, 0, "DENIED"),
                policy.decide(false, 100, 50));
    }

    @Test
    void rejectsInvalidDuration() {
        assertEquals(
                new ResumePolicy.Decision(false, 0, "UNAVAILABLE"),
                policy.decide(true, 0, 20));
        assertEquals(
                new ResumePolicy.Decision(false, 0, "UNAVAILABLE"),
                policy.decide(true, -1, 20));
    }

    @Test
    void startsWhenProgressIsMissing() {
        assertEquals(
                new ResumePolicy.Decision(true, 0, "START"),
                policy.decide(true, 100, null));
        assertEquals(
                new ResumePolicy.Decision(true, 0, "START"),
                policy.decide(true, 100, -2));
        assertEquals(
                new ResumePolicy.Decision(true, 0, "START"),
                policy.decide(true, 100, 0));
    }

    @Test
    void resumesBeforeFinalTenSeconds() {
        assertEquals(
                new ResumePolicy.Decision(true, 89, "RESUME"),
                policy.decide(true, 100, 89));
    }

    @Test
    void restartsAtBoundaryAndAfterIt() {
        assertEquals(
                new ResumePolicy.Decision(true, 0, "RESTART"),
                policy.decide(true, 100, 90));
        assertEquals(
                new ResumePolicy.Decision(true, 0, "RESTART"),
                policy.decide(true, 100, 101));
    }
}
~~~

**Vì sao chọn các trường hợp này?**

- **Không có quyền:** điều kiện ưu tiên cao, tránh vô tình trả tiến độ trái phép.
- **Thời lượng 0 hoặc âm:** bảo toàn cách xử lý đầu vào không hợp lệ.
- **Tiến độ null, 0 hoặc âm:** không thay ý nghĩa “chưa từng lưu”.
- **89 và 90 giây trên video 100 giây:** bảo vệ ranh giới ngay trước và tại ngưỡng.
- **Tiến độ 101 giây:** giữ hành vi cũ ở dữ liệu vượt thời lượng, dù nhóm có thể muốn điều chỉnh trong story khác.

Các kiểm thử này **chưa bảo đảm đầy đủ mọi tình huống trong production**. Nếu logic còn tác động đến quyền truy cập, thời gian thực, đồng thời, I/O hoặc hợp đồng API, nhóm cần thêm kiểm thử ở cấp tương ứng.

### 7.1. Đọc kết quả đúng cách

Nếu các kiểm thử đều Green trước và sau refactor, nhóm có **bằng chứng tốt hơn** rằng những hành vi được kiểm thử không đổi. Không thể suy rằng mọi hành vi đều tuyệt đối giống nhau chỉ từ một bộ kiểm thử hữu hạn.

Lưới an toàn phải đủ phù hợp với **phạm vi, mức rủi ro và những hợp đồng đang được phụ thuộc**.

### 7.2. Kết nối với Gherkin và yêu cầu người dùng

Những quy tắc tương đương có thể được làm rõ ở mức hành vi:

~~~gherkin
Feature: Tiếp tục video đã xem dở

Scenario: Người học có quyền và có vị trí hợp lệ
  Given người học được phép xem video dài 100 giây
  And hệ thống có vị trí đã lưu là 89 giây
  When người học mở lại video
  Then hệ thống chọn vị trí bắt đầu là 89 giây

Scenario: Người học bị từ chối quyền truy cập
  Given người học không được phép xem video
  When người học yêu cầu tiếp tục video
  Then hệ thống từ chối quyền phát
  And không cung cấp dữ liệu tiến độ trái quyền

Scenario: Vị trí nằm ở ranh giới mười giây cuối
  Given người học có quyền xem video dài 100 giây
  And hệ thống có vị trí đã lưu là 90 giây
  When người học mở lại video
  Then hệ thống chọn phát lại từ đầu theo quy tắc hiện hành
~~~

**Gherkin** giúp thảo luận hành vi với Product Owner và người hiểu nghiệp vụ; **JUnit** bảo vệ logic triển khai. TDD và refactoring không thay thế việc kiểm tra tính đúng đắn của yêu cầu đã thỏa thuận.

## 8. Một quy trình refactor thực tế từ đầu tới cuối

Không cần áp dụng đủ công cụ phức tạp cho mọi thay đổi. Quy trình dưới đây cung cấp một đường kiểm soát rõ ràng:

### Bước 1 — Xác định lý do cần refactor

Ví dụ: “Khi thêm một quy tắc cho người học chưa hoàn thành bài, chúng ta phải sửa cùng điều kiện trong ba service. Đây là nguy cơ thay đổi thiếu nhất quán.”

Tránh lý do mơ hồ: “Lớp này nhìn không thích, cần viết lại cho đẹp.”

### Bước 2 — Khoanh phạm vi và hợp đồng cần giữ

Xác định:

- Phương thức/API nào sẽ được chạm tới?
- Dữ liệu hoặc trạng thái nào người dùng/đối tác quan sát được?
- Các trường hợp biên và lỗi quan trọng là gì?
- Có yếu tố bảo mật, đồng thời, hiệu năng hay thời gian thực không?
- Có mã khách hàng hoặc job nền đang phụ thuộc hành vi hiện tại không?

### Bước 3 — Xây lưới an toàn

Chạy bộ kiểm thử hiện có. Nếu thiếu các trường hợp đặc biệt, bổ sung kiểm thử trước khi refactor. Với mã cũ, có thể bắt đầu bằng **characterization tests** để nắm bắt hành vi thực tế, rồi xác nhận chỗ nào phải giữ hoặc cần sửa nghiệp vụ riêng.

### Bước 4 — Chọn một phép tái cấu trúc nhỏ

Ví dụ: **Extract Method** cho một điều kiện, đổi tên phản ánh ý nghĩa hoặc đưa logic thuần tách khỏi truy cập dữ liệu.

Không gom đồng thời việc đổi framework, chuẩn hóa log, sửa lỗi, đổi API và di chuyển database vào một bước nếu không có lý do chặt chẽ.

### Bước 5 — Chạy kiểm tra và xem diff

- Kiểm thử nhanh liên quan.
- Kiểm thử tích hợp/contract khi chạm ranh giới.
- Linter, build hoặc kiểm tra tĩnh nếu pipeline dùng.
- Xem diff để phát hiện thay đổi nhánh điều kiện, hằng số, xử lý lỗi hoặc tác dụng phụ.

Nếu kết quả khác bất ngờ, **quay lại bước nhỏ vừa làm** trước khi tiếp tục. Một refactor có thể hoàn tác dễ dàng hữu ích hơn một bản thay đổi lớn khó xác định nguồn lỗi.

### Bước 6 — Tích hợp thường xuyên

Tạo commit nhỏ với mô tả mục đích rõ, review tập trung vào **tính tương đương hành vi và cải thiện cấu trúc**. Không giữ một nhánh refactor kéo dài nhiều tuần khi những người khác vẫn thay đổi cùng khu vực, nếu có cách chia nhỏ an toàn hơn.

### Bước 7 — Tiếp tục user story và đạt DoD

Refactoring không phải trạng thái cuối cùng của giá trị. Sau đó, nhóm thực hiện lát chức năng cần thiết, tích hợp, kiểm tra và đưa Increment tới điều kiện Done. Nếu thay đổi cấu trúc mang rủi ro đáng kể hoặc cần đầu tư riêng, nên làm minh bạch với PO và các bên liên quan.

### Mẫu kiểm tra trước khi merge

~~~text
Mục đích refactor:
  Cấu trúc nào gây khó thay đổi và cải thiện gì?

Phạm vi:
  File/module/hợp đồng nào thay đổi hoặc cần giữ nguyên?

Hành vi cần bảo toàn:
  Đầu ra, lỗi, quyền, dữ liệu, tác dụng phụ, tương thích.

Bằng chứng:
  Test trước/sau, integration/contract, kiểm tra ranh giới.

Rủi ro:
  Đồng thời, hiệu năng, cấu hình, migration, người dùng cũ.

Triển khai:
  Có cần chia commit, feature flag hoặc cách khôi phục?

Kết quả:
  Cấu trúc đơn giản hơn thế nào, còn gì chưa biết?
~~~

Mẫu này nên được rút gọn cho những refactor nhỏ. Mục tiêu là **minh bạch đủ để kiểm tra**, không tạo gánh nặng thủ tục.

## 9. Những kỹ thuật refactoring phổ biến và cách chọn

| Kỹ thuật | Khi nào hữu ích | Điều phải kiểm tra |
| --- | --- | --- |
| **Rename Variable/Method** | Tên mơ hồ hoặc không còn diễn đạt đúng nghiệp vụ. | Cách gọi từ bên ngoài, serialization, reflection, truy vấn động. |
| **Extract Method** | Một khối logic có ý nghĩa riêng và làm phương thức gốc khó đọc. | Thứ tự tác dụng phụ, biến bị thay đổi, ngoại lệ. |
| **Inline Method** | Phương thức trung gian chỉ làm điều hiển nhiên, tăng độ khó theo dõi. | Hành vi override, visibility, nơi được dùng. |
| **Extract Variable** | Biểu thức điều kiện phức tạp có ý nghĩa nghiệp vụ. | Không vô tình đánh giá biểu thức có tác dụng phụ nhiều/lệch lần. |
| **Replace Nested Conditional with Guard Clauses** | Nhiều nhánh lồng gây khó đọc luồng chính. | Thứ tự ưu tiên điều kiện và xử lý trường hợp biên. |
| **Move Method/Field** | Logic ở sai nơi giữ thông tin hoặc trách nhiệm. | Ranh giới public API, truy cập trạng thái, coupling. |
| **Extract Class** | Một lớp xử lý nhiều trách nhiệm có lý do thay đổi khác nhau. | Vòng đời đối tượng, giao dịch, thread safety. |
| **Introduce Parameter Object** | Nhóm tham số đi cùng nhau và có ý nghĩa chung. | Hợp đồng public, tương thích người gọi, bất biến dữ liệu. |
| **Replace Conditional with Polymorphism/Strategy** | Nhiều hành vi khác nhau thay đổi độc lập và có quy luật rõ. | Đừng tạo hệ phân cấp phức tạp nếu chỉ có hai điều kiện đơn giản. |
| **Encapsulate Collection** | Dữ liệu nội bộ bị sửa từ bên ngoài không qua bất biến nghiệp vụ. | Tính tương thích và cách người gọi đang dùng collection. |
| **Remove Duplication** | Nhiều chỗ phải thay cùng một quy tắc. | Đảm bảo quy tắc thực sự giống nhau về ý nghĩa, không chỉ giống cú pháp. |
| **Introduce Abstraction/Seam** | Cần tách phụ thuộc để kiểm thử hoặc thay triển khai. | Trừu tượng có rõ mục đích hay chỉ tăng lớp trung gian. |

### 9.1. Chọn theo chi phí thay đổi dự kiến

Ví dụ, nếu phải thêm một loại bài kiểm tra:

- Nếu chỉ có ba điều kiện đơn giản, một phương thức rõ ràng có thể đủ.
- Nếu mỗi loại bài có cách chấm, dữ liệu và tiêu chí riêng thường xuyên thay đổi, **Strategy** có thể giúp cô lập sự khác biệt.
- Nếu dữ liệu các loại bài cần giao dịch và tồn tại với nhiều phiên bản, việc chọn cấu trúc còn liên quan hợp đồng dữ liệu và migration, không chỉ refactor class.

Đừng chọn design pattern trước rồi đi tìm vấn đề phù hợp; hãy bắt đầu từ **điểm thay đổi thực tế và cách kiểm chứng**.

### 9.2. Đừng gộp trùng lặp quá sớm

Hai đoạn code giống nhau hôm nay nhưng thuộc **hai quy tắc độc lập** có thể thay đổi khác nhau ngày mai. Nếu gom vào một hàm chung với nhiều cờ điều khiển, mức coupling có thể tăng.

**Chỉ gộp khi có lý do chung về nghiệp vụ hoặc cấu trúc**, và có bằng chứng việc hợp nhất làm thay đổi dễ hơn thay vì ràng buộc các chức năng không liên quan.

## 10. Refactoring trong hệ thống legacy thiếu kiểm thử

Đây thường là trường hợp khó nhất: mã chạy lâu năm, ít tài liệu, phụ thuộc database và dịch vụ ngoài, kiểm thử yếu, ai cũng sợ sửa vì không biết ảnh hưởng.

### 10.1. Tránh viết lại toàn bộ ngay

Đề xuất “viết lại sạch từ đầu” có thể nghe hấp dẫn nhưng chứa rủi ro:

- Hành vi hiện tại có thể chứa các quy tắc ngầm chưa được tài liệu hóa.
- Chức năng mới vẫn tiếp tục phát sinh khi hệ thống mới chưa hoàn thành.
- Khó so sánh chính xác tương thích dữ liệu và khách hàng.
- Chưa chắc cấu trúc mới giải quyết đúng vấn đề khiến hệ thống cũ khó thay.
- Thời gian dài chưa có giá trị giao được sẽ tăng rủi ro kinh doanh.

Nên xem xét **cải tiến từng bước quanh nơi có thay đổi thực**, hoặc một chiến lược thay thế tăng dần khi thật sự cần thiết.

### 10.2. Characterization tests: mô tả hành vi đang có

**Characterization tests** ghi lại đầu vào và đầu ra hiện tại để giảm rủi ro thay đổi ngoài ý muốn. Chúng không tự xác nhận hành vi cũ là đúng theo nhu cầu người dùng.

Ví dụ, một hàm cũ trả về “RESTART” khi vị trí đã lưu bằng đúng **thời lượng trừ 10 giây**. Nếu không có đặc tả, kiểm thử trước tiên có thể bảo vệ hành vi thực đó. Sau khi làm rõ với PO, việc đổi ngưỡng mới là một **thay đổi chức năng riêng**.

Nguồn có thể dùng để quan sát:

- Ví dụ thực tế đã được người dùng xác nhận.
- Dữ liệu thử phù hợp, được xử lý quyền riêng tư.
- Kết quả API hiện hành và hợp đồng tích hợp.
- Log/sự kiện vận hành hợp lệ và đã được kiểm soát.
- Kiểm thử hiện có, kể cả trường hợp lỗi quan trọng.

Không nên chụp toàn bộ trạng thái production rồi biến thành golden snapshot một cách thiếu chọn lọc; nó có thể chứa dữ liệu nhạy cảm hoặc khóa chặt cả lỗi không cần giữ.

### 10.3. Tạo seam để tách phụ thuộc

**Seam** là điểm cho phép thay hoặc điều khiển một phụ thuộc trong kiểm thử hoặc quá trình chuyển đổi. Ví dụ, thay vì logic nghiệp vụ gọi trực tiếp hệ thống thanh toán từ nhiều chỗ, có thể đưa tương tác vào một ranh giới rõ để kiểm tra quyết định nghiệp vụ độc lập.

Đừng biến mọi đối tượng thành interface nếu không có nhu cầu thay thế hay kiểm thử. Chọn một **ranh giới đang gây khó khăn**, dùng trừu tượng tối thiểu đủ để kiểm soát nó.

### 10.4. Tập trung vào rủi ro cao trước

Ưu tiên kiểm thử và refactor ở phần có:

- Giao dịch tiền hoặc dữ liệu quan trọng.
- Phân quyền và quyền riêng tư.
- Logic đã từng gây sự cố.
- Phụ thuộc được dự báo sẽ thay trong các Sprint tới.
- Chi phí làm lại lớn nếu phát hiện sai muộn.

Một bước refactor nhỏ, an toàn và có khả năng đảo ngược thường tốt hơn một lần thay kiến trúc không có đường khôi phục.

## 11. Tái cấu trúc vượt ranh giới API, database và triển khai

Khi thay đổi chỉ nằm trong phương thức nội bộ, rủi ro thường được giới hạn bởi bộ kiểm thử. Khi chạm **API công khai, dữ liệu lưu trữ, sự kiện hoặc nhiều phiên bản đang chạy**, cần kiểm soát tương thích và triển khai nhiều bước.

**Cần phân biệt:** đổi cấu trúc code nội bộ là refactoring; di chuyển dữ liệu hoặc thay hợp đồng bên ngoài có thể là một **thay đổi hệ thống lớn hơn**, không được mặc nhiên gọi là refactoring thuần túy.

### 11.1. Expand–migrate–contract khi đổi cấu trúc dữ liệu

Giả sử hệ thống cần thay cách lưu tiến độ từ một trường cũ sang một mô hình có nhiều thiết bị. Có thể dùng tiến trình tăng dần:

| Giai đoạn | Thay đổi | Điều kiện kiểm soát |
| --- | --- | --- |
| **Expand** | Thêm cấu trúc mới có thể cùng tồn tại với dữ liệu hiện tại. | Phiên bản cũ vẫn chạy; thay đổi schema tương thích. |
| **Migrate** | Đọc/ghi hoặc đồng bộ theo chính sách rõ, chuyển dữ liệu dần. | Có kiểm tra tính nhất quán, lỗi, khôi phục và quyền truy cập. |
| **Verify** | Kiểm chứng dữ liệu, hiệu năng, xử lý xung đột và hành vi người dùng. | Có bằng chứng tương thích, không chỉ “migration đã chạy”. |
| **Contract** | Bỏ cấu trúc cũ khi mọi thành phần phụ thuộc đã chuyển an toàn. | Không còn client/job/phiên bản cũ đang cần dữ liệu cũ. |

Đây là **một chiến lược thay đổi hệ thống**, không phải cam kết mỗi bước luôn giữ toàn bộ hành vi nội bộ giống hệt. Mục tiêu là **giữ hợp đồng sử dụng bên ngoài phù hợp trong suốt quá trình chuyển đổi**.

### 11.2. Branch by abstraction

Khi cần thay một thành phần lớn, nhóm có thể tạo một ranh giới trừu tượng chung rồi đưa triển khai mới vào dần, thay vì duy trì nhánh code khổng lồ tách biệt rất lâu.

Cần xác định:

- Hợp đồng mà hai triển khai phải tuân thủ.
- Kiểm thử contract và dữ liệu biên.
- Cách chọn triển khai và cách giám sát.
- Phương án quay lại nếu có lỗi.
- Khi nào được loại bỏ code cũ.

**Feature flag** có thể hỗ trợ rollout có kiểm soát, nhưng không tự giải quyết tương thích dữ liệu, tác vụ bất đồng bộ hay tác động đã ghi vào hệ thống.

### 11.3. Không thay đổi API lén trong refactor

Đổi tên một trường JSON, thay HTTP status hoặc sửa thứ tự sự kiện có thể làm client không tương thích. Nếu muốn thay hợp đồng, cần:

- Nêu rõ yêu cầu và tác động.
- Chuẩn bị tương thích ngược hoặc phiên bản hóa khi cần.
- Thỏa thuận thời điểm và cách chuyển đổi.
- Kiểm tra bằng contract/integration tests.
- Truyền thông với người dùng hoặc hệ thống tích hợp.

Không nên gắn nhãn **refactor-only** để che một thay đổi có ảnh hưởng tới bên ngoài.

## 12. Những rủi ro ít thấy: đồng thời, hiệu năng và bảo mật

Refactoring có thể giữ nguyên các kiểm thử đơn vị nhưng vẫn phá những thuộc tính chỉ lộ ở môi trường phức tạp.

### 12.1. Thứ tự tác dụng phụ

Hai biểu thức điều kiện trông tương đương về logic nhưng khác thứ tự gọi dịch vụ có thể tạo kết quả khác nếu các lời gọi có tác dụng phụ.

Ví dụ, một phương thức vừa kiểm tra quyền vừa ghi log và gửi sự kiện. Nếu tái cấu trúc khiến việc gửi sự kiện diễn ra **trước khi kiểm tra quyền**, dữ liệu có thể bị lộ dù giá trị trả về cuối vẫn là “DENIED”.

**Cách bảo vệ:** kiểm thử tác dụng phụ và thứ tự sự kiện khi đó là hợp đồng, không chỉ kiểm tra giá trị trả về.

### 12.2. Đồng thời và giao dịch

Một đoạn code được tách thành hai hàm có thể vô tình thay ranh giới transaction, khóa hoặc thời điểm ghi dữ liệu. Với hệ thống đặt lịch, tính nhất quán khi **hai người cùng đặt một khung giờ** là điều kiện quan trọng.

**Cách bảo vệ:** kiểm thử tích hợp và thử cạnh tranh phù hợp, xác định bất biến dữ liệu, quan sát log và phương án xử lý khi lỗi.

### 12.3. Hiệu năng và tải

Cùng một kết quả nghiệp vụ nhưng cấu trúc mới có thể tạo thêm truy vấn, bộ nhớ hoặc độ trễ, chẳng hạn biến một truy vấn theo lô thành N+1 queries.

**Cách bảo vệ:** giữ ràng buộc hiệu năng quan trọng và đo trên tải đại diện khi thay đổi có nguy cơ ảnh hưởng.

### 12.4. Bảo mật và quyền riêng tư

Di chuyển logic phân quyền từ controller vào service có thể là refactor tốt, nhưng chỉ nếu **mọi đường gọi cần bảo vệ vẫn được kiểm tra**. Một endpoint khác hoặc job nền có thể đi qua đường code mới mà không áp điều kiện tương đương.

**Cách bảo vệ:** kiểm thử quyền truy cập ở ranh giới phù hợp, rà soát đường gọi và dùng nguyên tắc từ chối truy cập an toàn khi thiếu điều kiện.

## 13. Kỹ thuật XP hỗ trợ refactor liên tục như thế nào?

| Thực hành | Cách hỗ trợ | Giới hạn cần hiểu |
| --- | --- | --- |
| **TDD** | Kiểm thử nhanh bảo vệ hành vi và tạo phản hồi cho từng bước thay cấu trúc. | Kiểm thử kém có thể không nắm được hợp đồng thật. |
| **Pair Programming** | Hai người cùng hiểu quy tắc và phát hiện sai lệch ngay khi thay đổi. | Không thay kiểm thử và phản hồi từ người dùng. |
| **Continuous Integration** | Phát hiện lỗi tích hợp trong những thay đổi nhỏ thường xuyên. | Pipeline cần đủ độ tin cậy, không chỉ chạy build. |
| **Simple Design** | Giữ kiến trúc đơn giản cho nhu cầu hiện tại, tránh đầu tư giả định tương lai. | Đơn giản không đồng nghĩa bỏ những ràng buộc đã biết. |
| **Collective Code Ownership** | Giảm nút thắt “chỉ một người dám sửa khu vực này”, khuyến khích cải tiến chung. | Cần chuẩn code, kiểm thử và trao đổi để tránh sửa thiếu hiểu biết. |
| **Coding Standards** | Làm code dễ đọc thống nhất, giảm chi phí chuyển ngữ cảnh và review. | Không biến sở thích định dạng thành các tranh cãi vô tận. |
| **Small Releases** | Giảm lô thay đổi, cho cơ hội nhận phản hồi sớm. | Release cần đạt điều kiện chất lượng và vận hành. |
| **Sustainable Pace** | Giữ khả năng suy nghĩ, kiểm tra và cải tiến lâu dài. | Không lấy “nhanh” làm lý do làm ngoài giờ thường xuyên. |

Một nhóm có thể có CI rất tốt nhưng hệ thống thiết kế vẫn khó thay vì liên tục sao chép logic. Ngược lại, refactor nhiều nhưng không tích hợp sớm sẽ gây xung đột và rủi ro. **Các thực hành cần hỗ trợ nhau thành một vòng học hỏi**, không tồn tại như checkbox độc lập.

## 14. Gắn refactoring vào Scrum, Kanban và kế hoạch sản phẩm

Refactoring thường không trực tiếp thể hiện một user story mới, nhưng nó ảnh hưởng khả năng tạo Increment trong tương lai. Cần quản lý **minh bạch và theo giá trị**, tránh hai thái cực: “mọi refactor đều phải xin một dự án riêng” hoặc “Developers có thể dành cả Sprint dọn code mà không trao đổi”.

### 14.1. Refactoring nhỏ trong một user story

Khi thực hiện một lát “Học tiếp”, Developers cần thêm một quy tắc mới vào mã tiến độ. Nhóm thấy cấu trúc điều kiện lồng khiến thay đổi dễ sai. Họ có thể:

1. Bổ sung kiểm thử hồi quy.
2. Refactor phương thức liên quan.
3. Thực hiện hành vi mới với kiểm thử.
4. Đưa toàn bộ phần thay đổi tới DoD.

Đây là **công việc kỹ thuật cần thiết để tạo Increment có chất lượng**. Không phải mọi lần đổi tên biến đều cần Product Backlog Item riêng.

### 14.2. Cải tiến có phạm vi lớn hoặc có rủi ro đáng kể

Nếu nhiều nhóm cần thay ranh giới giữa các dịch vụ, di chuyển dữ liệu hoặc gỡ một phụ thuộc kiến trúc kéo dài, công việc có thể:

- Cần thời gian và năng lực được dự kiến rõ.
- Ảnh hưởng phạm vi sản phẩm hoặc thời điểm phát hành.
- Cần phối hợp với vận hành/bảo mật hoặc đối tác.
- Có thể tạo một **enabler/technical backlog item** với tiêu chí kết thúc và lý do rõ ràng.

Product Owner cần thông tin để quản lý Product Backlog hiệu quả và tối đa hóa giá trị; Developers góp hiểu biết kỹ thuật, rủi ro và phương án. Nhãn “technical” **không có nghĩa tự động ưu tiên thấp**, nhưng cũng không tự động ưu tiên cao hơn nhu cầu người dùng.

### 14.3. Scrum: bảo toàn Sprint Goal và Definition of Done

Trong Scrum:

- **Product Owner** chịu trách nhiệm giá trị và thứ tự Product Backlog.
- **Developers** tự quản kế hoạch thực hiện, tạo Increment đáp ứng **Definition of Done**.
- **Scrum Master** hỗ trợ hiệu quả Scrum, giảm trở ngại và cải thiện phối hợp.
- **Sprint Goal** định hướng lựa chọn công việc và cách thích ứng trong Sprint.
- **Sprint Review** giúp học từ kết quả và thay đổi ưu tiên.
- **Sprint Retrospective** là dịp quan sát điểm nghẽn kỹ thuật và thử cải tiến cách làm.

Nếu refactoring giúp một story đạt DoD an toàn, nó là một phần năng lực kỹ thuật để đạt Sprint Goal. Nếu phát sinh refactor lớn chưa dự kiến, nhóm cần **nêu tác động và thảo luận phạm vi**, không âm thầm kéo dài Sprint hoặc giảm DoD.

**Increment đã Done có thể được bàn giao trước Sprint Review** khi điều kiện phát hành phù hợp; refactoring và CI tốt hỗ trợ khả năng đó nhưng không tự quyết định thời điểm release.

### 14.4. Kanban: quản lý luồng, không tích lũy “dọn code dở”

Với Kanban, có thể trực quan hóa công việc refactor đáng kể theo cùng chính sách WIP hoặc một loại việc có chính sách rõ, đo cycle time và work item age, tránh mở đồng thời quá nhiều thay đổi cấu trúc.

Ví dụ:

~~~text
Ready -> Develop (WIP <= 3) -> Review (WIP <= 2) -> Verify -> Done

PBI-A: hoàn thiện luồng xem tiến độ
PBI-B: tách phụ thuộc API để kiểm thử hợp đồng
PBI-C: sửa lỗi phân quyền khẩn theo chính sách riêng
~~~

Đây là ví dụ bảng, các WIP limit chỉ minh họa. Nhóm cần thấy **công việc nào thật sự gần Done** và xử lý điểm nghẽn thay vì cứ thêm hạng mục refactor vào “In progress”.

### 14.5. Tránh cơ chế “Sprint kỹ thuật” mặc định

Đôi khi tổ chức muốn dành nguyên Sprint cuối quý cho “dọn nợ kỹ thuật”. Cách này có thể cần trong tình huống đặc biệt, nhưng nếu mọi Sprint còn lại đều mặc kệ cấu trúc, chi phí thay đổi sẽ tích lũy liên tục.

Tốt hơn là **đưa chất lượng và refactoring cần thiết vào nhịp phát triển thông thường**, đồng thời quản lý minh bạch các khoản nợ kiến trúc lớn cần kế hoạch riêng.

## 15. Nợ kỹ thuật và refactoring: có liên hệ nhưng không đồng nhất

**Nợ kỹ thuật (technical debt)** là cách nói về chi phí phát sinh trong tương lai từ lựa chọn thiết kế/triển khai khiến việc thay đổi, bảo trì hoặc vận hành khó hơn. Không phải mọi nợ kỹ thuật đều giải quyết bằng refactoring.

Ví dụ:

| Vấn đề | Có thể cần giải pháp nào? | Chỉ refactor code có đủ không? |
| --- | --- | --- |
| Logic khôi phục tiến độ bị sao chép ở bốn service. | Gom quy tắc và kiểm thử hành vi. | **Có thể** đủ nếu giữ hợp đồng. |
| Không có kiểm thử tích hợp cho quyền truy cập. | Xây kiểm thử, chỉnh DoD, rà soát rủi ro. | **Không**; thiếu lưới an toàn. |
| Database cũ không đáp ứng khối lượng dữ liệu mới. | Đánh giá mô hình dữ liệu, migration, hiệu năng và vận hành. | **Không tự động**. |
| API công khai có hợp đồng mơ hồ với đối tác. | Thống nhất contract, versioning và kiểm thử tương thích. | **Không** nếu cần đổi hợp đồng. |
| Mã khó đọc vì tên biến và phương thức lồng nhau. | Rename, Extract Method, giảm điều kiện lồng. | **Có thể**, sau khi kiểm chứng. |
| Môi trường CI chạy chậm và thường thất bại ngẫu nhiên. | Cải thiện pipeline, test isolation và hạ tầng. | Không phải chỉ là refactor production code. |
| Quy trình phê duyệt khiến release chờ nhiều ngày. | Cải tiến tổ chức/luồng quyết định. | Không thuộc refactoring mã. |

### 15.1. Ưu tiên theo chi phí trì hoãn và khả năng giảm rủi ro

Hãy hỏi:

- Vấn đề đang cản những user story hoặc mục tiêu nào?
- Nếu không làm, loại chi phí nào có thể tăng?
- Phạm vi sửa nhỏ nhất đủ tạo cải thiện là gì?
- Có cần thêm kiểm thử trước không?
- Kết quả nào chứng minh khoản đầu tư đáng giá?
- Khi nào nên xem lại nếu chưa đủ dữ liệu?

Không nên gán một “điểm nợ kỹ thuật” tùy ý rồi dùng nó như con số quyết định tuyệt đối. Cần bối cảnh về giá trị, rủi ro và khả năng thay đổi.

## 16. Đo khả năng thay đổi trước và sau refactoring

Không thể kết luận refactor thành công chỉ vì **giảm 500 dòng**, **tạo thêm 20 interface** hoặc **đạt một điểm quality gate**. Những tín hiệu đó có thể hữu ích, nhưng không trực tiếp chứng minh giá trị.

### 16.1. Chỉ số gắn với khả năng thay đổi

| Góc nhìn | Câu hỏi | Tín hiệu có thể dùng |
| --- | --- | --- |
| **Độ tập trung của thay đổi** | Một quy tắc mới cần sửa bao nhiêu điểm? | Số nơi cần chỉnh cho cùng một yêu cầu, mức độ coupling có ý nghĩa. |
| **Thời gian hoàn tất** | Một lát giá trị có đi qua Dev–Review–Verify nhanh hơn với DoD không đổi? | Cycle time, blocked time, work item age theo loại việc tương tự. |
| **Chất lượng** | Có ít lỗi hồi quy, sửa lại và sự cố nghiêm trọng hơn không? | Defect trends, số lần sửa sau review, lỗi production có phân loại. |
| **Khả năng kiểm chứng** | Có thể chạy kiểm thử hữu ích nhanh, ổn định và độc lập hơn không? | Thời gian phản hồi CI, độ ổn định kiểm thử, mức bao phủ các hành vi rủi ro. |
| **Khả năng cộng tác** | Người khác có thể hiểu và sửa khu vực code dễ hơn không? | Review có chất lượng, phụ thuộc một cá nhân, phản hồi từ người thực hiện. |
| **Khả năng dự báo** | Công việc ở khu vực này có ít bất định gây bất ngờ hơn không? | Phân bố cycle time, blocked items, phụ thuộc phát sinh. |
| **Giá trị sản phẩm** | Nhóm có thể giao và học từ thay đổi hữu ích sớm hơn không? | Thời gian từ ý tưởng đến phản hồi, tỷ lệ người dùng hoàn thành tác vụ. |

### 16.2. Ví dụ trước/sau có điều kiện

Giả sử trước refactoring, nhóm sửa quy tắc tiến độ trong bốn nơi khác nhau; một user story liên quan thường phải sửa lỗi tích hợp nhiều vòng. Sau refactor, quy tắc nằm ở một nơi, kiểm thử hợp đồng tốt hơn và những story tương tự cần ít vòng review hơn.

Đây là dấu hiệu khả quan, nhưng để quy nguyên nhân hợp lý cần xem:

- Hai giai đoạn có loại việc tương đương không?
- Definition of Done có giữ nguyên không?
- Nhóm có thêm người kinh nghiệm hoặc thay công cụ không?
- Số story và cỡ mẫu có đủ đại diện không?
- Việc giảm thời gian có đi kèm tăng lỗi ở nơi khác không?

Không nên tuyên bố “refactor tăng năng suất 40%” nếu chỉ có một vài ví dụ không đối chứng.

### 16.3. Chỉ số cần tránh dùng làm mục tiêu cá nhân

- Số dòng code bị xóa hoặc thêm.
- Số phương thức/class được tạo sau refactor.
- Số commit mang nhãn refactor.
- Story points do một cá nhân hoàn thành.
- Tỷ lệ coverage cao mà không xét chất lượng kiểm thử.
- Số lỗi phát hiện được gán hoàn toàn cho một người.

Khi biến những con số này thành chỉ tiêu thưởng phạt, nhóm có thể **tối ưu chỉ số thay vì khả năng thay đổi thật**.

## 17. Tình huống thực tế: thêm quy tắc “xem lại 5 giây”

Nhóm đã refactor **ResumePolicy** và có kiểm thử bảo vệ hành vi. Giờ Product Owner nhận phản hồi: nhiều người học muốn video **lùi lại 5 giây** khi tiếp tục để lấy ngữ cảnh.

### 17.1. Vì sao đây không còn là refactoring thuần túy?

Trước đây, tiến độ 60 giây trên video dài 100 giây trả vị trí **60**. Theo yêu cầu mới, có thể trả **55**. Đây là **hành vi bên ngoài đã đổi**, cần user story/acceptance criteria và kiểm thử mới.

Refactoring trước đó mang giá trị vì logic rõ ràng và dễ xác định điểm cần thay, nhưng không được gọi chính thay đổi vị trí 60 → 55 là “dọn code”.

### 17.2. Cách thực hiện an toàn

1. PO/Developers làm rõ quy tắc: lùi 5 giây áp dụng cho những trường hợp nào?
2. Thống nhất giới hạn: không trả vị trí âm; trường hợp START và RESTART có lùi không?
3. Viết kiểm thử mô tả hành vi mới (**Red**).
4. Thực hiện thay đổi tối thiểu để kiểm thử đạt (**Green**).
5. Refactor cấu trúc nếu cần mà không đổi thêm hành vi (**Refactor**).
6. Chạy kiểm thử hồi quy, tích hợp và kiểm tra DoD.
7. Giao lát nhỏ, thu phản hồi về trải nghiệm.

Ví dụ acceptance criteria cho trường hợp không ở gần cuối:

~~~gherkin
Feature: Lùi lại để lấy ngữ cảnh khi tiếp tục học

Scenario: Tiếp tục từ vị trí có đủ thời gian phía trước
  Given người học có quyền xem video dài 100 giây
  And hệ thống đã lưu tiến độ 60 giây
  When người học chọn tiếp tục video
  Then vị trí bắt đầu theo quy tắc mới là 55 giây

Scenario: Không để vị trí bắt đầu âm
  Given người học có quyền xem video dài 100 giây
  And hệ thống đã lưu tiến độ 3 giây
  When người học chọn tiếp tục video
  Then vị trí bắt đầu không nhỏ hơn 0
~~~

**Lưu ý:** đây là đề xuất hành vi **mới**, không phải bằng chứng ResumePolicy ở phần 6 đã triển khai nó. Các trường hợp ngưỡng cuối video, tiến độ không hợp lệ và chính sách lưu cần được nhóm làm rõ trước khi thay.

### 17.3. Liên hệ tới khả năng thay đổi

Nếu nhóm có thể sửa tại một điểm rõ ràng, thêm hai hoặc ba kiểm thử liên quan và tích hợp an toàn, đó là một bằng chứng thực tế rằng refactoring trước đã giúp **giảm ma sát khi thêm giá trị**.

## 18. Anti-patterns khi “refactor liên tục”

| Anti-pattern | Hậu quả | Cách xử lý |
| --- | --- | --- |
| **Big-bang cleanup** | Đổi hàng trăm file cùng lúc, khó review và xác định lỗi. | Chia thành những bước nhỏ, tương thích, có thể hoàn tác. |
| **Refactor không có lưới an toàn** | Dễ thay hành vi ngoài ý muốn. | Viết kiểm thử ở phạm vi rủi ro trước; kiểm chứng sau mỗi bước. |
| **Sửa bug lẫn refactor mà không nói rõ** | Review và tìm lỗi khó, hợp đồng có thể thay ngầm. | Tách thay đổi hành vi và cấu trúc, mô tả mục đích riêng. |
| **Thêm abstraction cho tương lai tưởng tượng** | Tăng số lớp và coupling, hiểu code khó hơn. | Ưu tiên thiết kế đơn giản đủ cho nhu cầu đã biết. |
| **Gộp logic giống cú pháp nhưng khác nghiệp vụ** | Hai quy tắc độc lập bị khóa chung. | Chỉ gộp khi có chung lý do thay đổi. |
| **Refactor khu vực không ai dùng trong khi tính năng chính bị chặn** | Mất cơ hội giao giá trị, ưu tiên mơ hồ. | Dựa trên tác động và rủi ro thực tế, phối hợp Product Backlog. |
| **Bỏ DoD để lấy thời gian dọn code** | Giảm chất lượng, tạo thêm nợ kỹ thuật. | Giữ DoD; thương lượng phạm vi nếu không đủ năng lực. |
| **Duy trì nhánh refactor quá lâu** | Xung đột tích hợp, kiểm thử lỗi thời. | Tích hợp sớm, branch by abstraction khi cần. |
| **Tin rằng mọi test Green là bảo đảm tuyệt đối** | Bỏ sót tương thích, dữ liệu, đồng thời hoặc bảo mật. | Kiểm thử hợp đồng và rủi ro ở cấp phù hợp. |
| **Dùng static metrics thay cho đánh giá thiết kế** | Tối ưu số liệu, code có thể phức tạp hơn. | Kết hợp review, độ rõ, khả năng thay đổi và kết quả. |
| **Đổ lỗi tác giả code cũ** | Giảm hợp tác, người ta ngại nêu rủi ro. | Xem lại bối cảnh lịch sử, cải tiến thiết kế chung. |
| **Không dành thời gian refactor vì “không tạo tính năng”** | Chi phí sửa lỗi và thay đổi tiếp tục tăng. | Tính chi phí kỹ thuật trong kế hoạch tạo giá trị và DoD. |

## 19. Bài tập thực hành: tái cấu trúc mà không thay đổi hành vi

Một nhóm đang xây nền tảng học Java. Phương thức sau xử lý trạng thái kết quả kiểm tra:

~~~java
public final class QuizStatus {
    public String status(
            boolean submitted,
            Integer score,
            boolean reviewed) {

        if (submitted) {
            if (score == null) {
                return "PENDING_SCORE";
            }
            if (reviewed) {
                if (score >= 80) {
                    return "PASSED_REVIEWED";
                }
                return "RETRY_REVIEWED";
            }
            if (score >= 80) {
                return "PASSED";
            }
            return "RETRY";
        }
        return "NOT_SUBMITTED";
    }
}
~~~

**Yêu cầu hiện tại:** phải giữ nguyên đầu ra cho mọi trường hợp được mô tả. Việc sửa logic nghiệp vụ sẽ là một story khác.

### Nhiệm vụ

1. **Mô tả hành vi:** Tạo bảng trường hợp cho **submitted**, **score** (null, 79, 80) và **reviewed**.
2. **Nhận diện smell:** Điều kiện nào lặp lại? Phương thức đang khó đọc ở đâu? Có smell nào **không cần** sửa không?
3. **Kiểm thử trước:** Viết tối thiểu sáu kiểm thử bảo vệ các nhánh và ngưỡng 80.
4. **Refactor:** Đề xuất một phép **Extract Method** hoặc guard clauses để làm rõ logic.
5. **Kiểm tra:** So sánh đầu ra trước/sau, chú ý trường hợp **score null** và **submitted=false**.
6. **Giới hạn:** Nếu người dùng muốn đổi ngưỡng 80 thành 75, nên tổ chức thay đổi đó như thế nào?
7. **Luồng công việc:** Nếu PR refactor chờ review ba ngày nhưng viết code một giờ, nhóm nên tập trung cải thiện điểm nào?
8. **Đo kết quả:** Đề xuất một tín hiệu về khả năng thay đổi, một số đo dòng công việc và một dấu hiệu chất lượng.

### Một phương án refactor tham khảo

~~~java
public final class QuizStatus {
    public String status(
            boolean submitted,
            Integer score,
            boolean reviewed) {

        if (!submitted) {
            return "NOT_SUBMITTED";
        }
        if (score == null) {
            return "PENDING_SCORE";
        }
        if (reviewed) {
            return reviewedStatus(score);
        }
        return unreviewedStatus(score);
    }

    private String reviewedStatus(int score) {
        return score >= 80 ? "PASSED_REVIEWED" : "RETRY_REVIEWED";
    }

    private String unreviewedStatus(int score) {
        return score >= 80 ? "PASSED" : "RETRY";
    }
}
~~~

Phương án này giữ nguyên:

- **NOT_SUBMITTED** nếu chưa nộp, kể cả khi có score hoặc reviewed=true.
- **PENDING_SCORE** khi đã nộp nhưng score=null, bất kể reviewed.
- Ngưỡng **score >= 80** và các chuỗi trạng thái.
- Phân nhánh reviewed và chưa reviewed.

Nó **không** thêm kiểu enum hay thay API công khai; những cải tiến kiểu dữ liệu có thể xem xét sau nếu cần và có kế hoạch tương thích.

### Kiểm thử JUnit tham khảo

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class QuizStatusTest {
    private final QuizStatus quiz = new QuizStatus();

    @Test
    void preservesBranchesAndBoundary() {
        assertEquals("NOT_SUBMITTED", quiz.status(false, 99, true));
        assertEquals("PENDING_SCORE", quiz.status(true, null, true));
        assertEquals("PENDING_SCORE", quiz.status(true, null, false));

        assertEquals("RETRY", quiz.status(true, 79, false));
        assertEquals("PASSED", quiz.status(true, 80, false));

        assertEquals("RETRY_REVIEWED", quiz.status(true, 79, true));
        assertEquals("PASSED_REVIEWED", quiz.status(true, 80, true));
    }
}
~~~

Việc chuyển ngưỡng từ 80 thành 75 phải được quản lý **như thay đổi hành vi riêng**, có yêu cầu và kiểm thử mới. Nếu thời gian chờ review là nút thắt chính, cải thiện chính sách review, kích thước PR hoặc WIP có thể đem lại hiệu quả lớn hơn việc gõ code nhanh thêm vài phút.

## 20. Tự kiểm tra kiến thức

**Câu 1.** Refactoring có phải là sửa code để người dùng nhận được một chức năng mới?

**Đáp án:** Không. Refactoring cải thiện cấu trúc bên trong và giữ hành vi bên ngoài; thêm chức năng mới là thay đổi hành vi và nên được kiểm chứng riêng.

**Câu 2.** Trong TDD, ở bước Refactor có cần cố ý viết một kiểm thử thất bại mới không?

**Đáp án:** Không. Red dùng để mô tả **hành vi mới** trước khi triển khai; bước Refactor cải thiện thiết kế khi các kiểm thử đang Green và phải giữ chúng Green.

**Câu 3.** Vì sao một đoạn logic trùng lặp ở hai nơi không tự động phải gộp?

**Đáp án:** Hai đoạn có thể đại diện cho các quy tắc nghiệp vụ độc lập. Gộp quá sớm tạo coupling không cần thiết; cần xem lý do thay đổi và ý nghĩa thực tế.

**Câu 4.** Mọi kiểm thử đơn vị đều đạt sau refactor. Có thể bỏ qua kiểm thử API và phân quyền không?

**Đáp án:** Không mặc định. Lưới an toàn phải phù hợp phạm vi và rủi ro. Nếu thay đổi chạm hợp đồng, trạng thái, quyền hoặc tương tác ngoài, cần kiểm chứng ở cấp phù hợp.

**Câu 5.** Đổi mã phản hồi từ “DENIED” thành “NO_ACCESS” có phải refactor thuần túy không?

**Đáp án:** Không nếu người gọi đang dựa vào chuỗi đó. Đây là thay đổi hợp đồng hoặc hành vi quan sát được, cần quản lý và kiểm thử riêng.

**Câu 6.** Một phần code được sửa mỗi Sprint, nhiều người né vì khó hiểu; refactoring ở đây có thể tạo giá trị gì?

**Đáp án:** Giảm rủi ro thay đổi, chi phí đọc/kiểm thử và công việc làm lại; cải thiện khả năng giao các lát giá trị trong những Sprint tiếp theo.

**Câu 7.** Đổi cấu trúc dữ liệu production có thể coi là an toàn chỉ vì unit tests Green không?

**Đáp án:** Không. Cần đánh giá migration, tương thích phiên bản, dữ liệu thật, giao dịch, phương án khôi phục và kiểm thử tích hợp.

**Câu 8.** Có nên dành nhiều ngày refactor một module không còn thay đổi chỉ vì static analyzer chấm điểm thấp?

**Đáp án:** Không nên mặc định. Phải xem giá trị, rủi ro, mức sử dụng và chi phí cơ hội. Có thể trì hoãn nếu không ảnh hưởng mục tiêu hoặc chất lượng cần thiết.

**Câu 9.** Sprint Goal và DoD có thể bỏ qua để làm “Sprint dọn code” cho nhanh không?

**Đáp án:** Không. Cần minh bạch mục tiêu và phạm vi, thương lượng công việc với Product Owner khi tác động đáng kể; giữ tiêu chuẩn DoD cho Increment.

**Câu 10.** Vì sao số dòng code giảm không đủ chứng minh refactoring thành công?

**Đáp án:** Code ngắn hơn vẫn có thể khó hiểu, coupling cao hoặc làm thay đổi hành vi. Cần xem cấu trúc, khả năng sửa, chất lượng và dữ liệu giao hàng.

**Câu 11.** Để tránh chi phí rewrite lớn, nhóm legacy có thể bắt đầu từ đâu?

**Đáp án:** Chọn vùng có thay đổi thực, nắm bắt hành vi bằng characterization tests, tạo seam cần thiết, refactor từng bước nhỏ và kiểm tra tương thích.

**Câu 12.** Khi kiểm thử phát hiện hành vi cũ có lỗi, có nên sửa ngay trong commit refactor không?

**Đáp án:** Nên ghi nhận, xác minh hành vi mong muốn và thực hiện bản sửa lỗi riêng hoặc thay đổi được tách rõ. Không che một thay đổi nghiệp vụ dưới nhãn refactor-only.

## 21. Checklist áp dụng trong công việc hằng ngày

Có thể dùng nhanh trước một pull request chứa refactoring:

### Trước khi sửa

- [ ] Tôi giải thích được **khó khăn khi thay đổi** mà refactor này cần giải quyết.
- [ ] Đã xác định ranh giới hành vi và hợp đồng cần giữ.
- [ ] Có kiểm thử phù hợp, hoặc có kế hoạch bổ sung lưới an toàn trước khi sửa.
- [ ] Đã nhận diện rủi ro dữ liệu, quyền truy cập, đồng thời, hiệu năng và phụ thuộc nếu liên quan.
- [ ] Phạm vi đủ nhỏ, hoặc đã có kế hoạch chia bước an toàn.

### Trong khi sửa

- [ ] Mỗi bước chỉ nhắm tới một cải thiện cấu trúc có ý nghĩa.
- [ ] Không âm thầm đổi quy tắc nghiệp vụ, thông báo lỗi hoặc hợp đồng API.
- [ ] Kiểm thử được chạy sau các bước quan trọng và khi tích hợp.
- [ ] Diff có thể review, thay đổi có thể hoàn tác tương đối dễ.
- [ ] Không tạo lớp/trừu tượng mới chỉ vì dự đoán tương lai chưa có bằng chứng.

### Trước khi hoàn tất

- [ ] Kiểm thử hành vi, tích hợp và các trường hợp rủi ro phù hợp đã đạt.
- [ ] Definition of Done và tiêu chuẩn chất lượng áp dụng vẫn được giữ.
- [ ] Pull request mô tả vì sao cấu trúc mới dễ thay đổi hơn.
- [ ] Thay đổi chức năng/bug fix (nếu có) được tách hoặc ghi rõ và kiểm chứng.
- [ ] Không bỏ sót kế hoạch triển khai, migration, theo dõi lỗi hoặc rollback khi cần.
- [ ] Người liên quan có thể hiểu tác động tới phạm vi Sprint/release nếu refactor đáng kể.

### Sau khi áp dụng

- [ ] Cải tiến có giải quyết được điểm khó đã nêu không?
- [ ] Việc thêm hành vi tiếp theo có ít thay đổi lan rộng hơn không?
- [ ] Cycle time, blocked time, lỗi hoặc làm lại có chuyển biến có ý nghĩa không?
- [ ] Có phát sinh phức tạp hoặc rủi ro mới cần điều chỉnh không?

Checklist là công cụ hỗ trợ đối thoại, **không phải một loạt cổng phê duyệt bắt buộc cho mọi đổi tên biến**.

## 22. Ghi nhớ trọng tâm

- **Refactoring thay đổi cấu trúc bên trong nhưng bảo toàn hành vi quan sát được.** Nó khác thêm tính năng, sửa lỗi, tối ưu hiệu năng và thay hợp đồng.
- **Trong XP, refactoring là việc nhỏ được thực hiện liên tục**, thường đan xen với TDD, CI, lập trình cặp và thiết kế đơn giản, thay vì dồn thành một lần viết lại lớn.
- **Red–Green–Refactor** giữ rõ ranh giới: thêm hành vi với kiểm thử, sau đó cải thiện cấu trúc khi các kiểm thử đang Green.
- **Code smells là tín hiệu**, không phải danh sách việc phải sửa bằng mọi giá. Chọn theo ảnh hưởng đến khả năng thay đổi và rủi ro.
- **Refactor an toàn cần lưới kiểm thử phù hợp**, gồm trường hợp biên, quyền truy cập, tác dụng phụ và hợp đồng ngoài khi cần; Green không phải bằng chứng tuyệt đối.
- **Mã legacy nên được cải thiện từng bước**, bắt đầu bằng characterization tests, seam và các vùng thường thay đổi, không mặc định viết lại toàn bộ.
- **API, database và triển khai nhiều phiên bản** đòi hỏi kiểm soát tương thích, migration và phương án khôi phục; đó có thể vượt phạm vi refactoring thuần túy.
- **Refactoring có thể nằm trong công việc user story**; các thay đổi kiến trúc lớn cần được quản lý minh bạch với Product Backlog và tác động tới Sprint Goal.
- **Kanban giúp nhìn WIP và thời gian chờ; Scrum giữ mục tiêu và DoD; XP giữ kỹ thuật để thay đổi đáng tin.** Các cách làm bổ trợ nhau.
- **Không đo thành công bằng số dòng bị xóa hay story points cá nhân.** Hãy xem khả năng sửa an toàn, chất lượng, dòng giao hàng và kết quả sản phẩm.
- **Đơn giản hóa để đáp ứng nhu cầu hiện tại, nhưng không bỏ ràng buộc đã biết.** Refactoring tốt làm cho lần thay đổi tiếp theo dễ hiểu, dễ kiểm chứng và ít rủi ro hơn.

Tái cấu trúc liên tục không có nghĩa cả nhóm dành mọi ngày để “làm đẹp code”. Nó là kỷ luật **không để những thay đổi có giá trị hôm nay làm mất khả năng thay đổi ngày mai**. Khi cấu trúc được cải thiện qua các bước nhỏ có kiểm thử, nhóm có thể giao phần mềm tăng dần, lấy phản hồi sớm và tiếp tục thích ứng với nhu cầu người dùng mà không phải trả giá bằng những lần viết lại đầy rủi ro.
