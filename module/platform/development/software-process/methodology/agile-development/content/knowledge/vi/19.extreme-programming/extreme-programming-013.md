# Quan hệ hỗ trợ lẫn nhau giữa các thực hành XP

> **Thông điệp chính:** Extreme Programming (XP) không phải một bộ mẹo kỹ thuật độc lập để chọn ngẫu nhiên. Các thực hành như **phát triển hướng kiểm thử (TDD), thiết kế đơn giản, refactoring, lập trình cặp, sở hữu mã tập thể, quy ước mã, tích hợp liên tục, phát hành nhỏ, kiểm thử chấp nhận và cộng tác thường xuyên với khách hàng** tạo thành những **vòng phản hồi hỗ trợ lẫn nhau**. Một thực hành giúp thực hành khác trở nên an toàn, hiệu quả hoặc khả thi hơn; khi thiếu mắt xích quan trọng, giá trị của cả hệ thống có thể giảm.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **mục đích của XP**: cải thiện khả năng giao phần mềm có giá trị và thích ứng với yêu cầu thay đổi bằng phản hồi thường xuyên, chất lượng kỹ thuật và cộng tác.
2. Mô tả ít nhất **bốn mối quan hệ tương hỗ** giữa những thực hành XP, thay vì chỉ kể tên chúng.
3. Phân tích vòng **TDD → refactoring → thiết kế đơn giản → thay đổi nhỏ → kiểm thử lại** và điều kiện để vòng này phát huy tác dụng.
4. Giải thích vì sao **pair programming, coding standards, collective code ownership và CI** có thể giúp nhóm cùng sửa mã mà không tạo hỗn loạn.
5. Kết nối **small releases, user stories, acceptance tests, khách hàng sẵn sàng phản hồi và lập kế hoạch ngắn hạn** với việc kiểm chứng giá trị người dùng.
6. Nhận diện khi nào sự phối hợp các thực hành bị đứt gãy: test chậm, nhánh tích hợp lâu, chỉ một người dám sửa module, yêu cầu mơ hồ hoặc phát hành quá lớn.
7. Đề xuất cách áp dụng XP từng bước, theo dõi **chất lượng, dòng công việc và kết quả sản phẩm**, không biến một thực hành thành KPI mang tính nghi thức.
8. Vận dụng các vòng hỗ trợ vào ví dụ lưu tiến độ học tập, đồng thời phân biệt XP với Scrum, Kanban và các yêu cầu quản trị ngoài nhóm.

## 2. Vì sao học riêng từng thực hành có thể gây hiểu nhầm?

Một nhóm phát triển nền tảng học trực tuyến nghe nói XP giúp tăng chất lượng và tốc độ phản hồi. Họ thử áp dụng:

- Viết thêm unit test cho một số class.
- Cho hai người ngồi chung khi gặp lỗi phức tạp.
- Thiết lập pipeline CI chạy mỗi đêm.
- Sắp xếp một buổi demo cuối tháng.

Những thay đổi này có thể hữu ích, nhưng nhóm vẫn gặp vấn đề:

- Code thay đổi lớn, tích hợp muộn, test chạy chậm.
- Test phụ thuộc quá nhiều vào chi tiết triển khai nên mỗi lần refactor lại vỡ hàng loạt.
- Chỉ tác giả ban đầu dám sửa module lưu tiến độ.
- Product Owner thấy demo chạy đúng nhưng phát hiện người học vẫn mất tiến độ khi mạng yếu.
- Nhiều PBI được báo Done dù chưa có Increment tích hợp và đáp ứng chuẩn chất lượng.

Vấn đề không nhất thiết là “TDD không hiệu quả” hay “pair programming quá tốn người”. Có thể nhóm mới áp dụng **hình thức của một thực hành mà thiếu những điều kiện và thực hành bổ trợ**.

Ví dụ:

> **TDD** giúp tạo lưới an toàn cho **refactoring**. **Refactoring** giữ thiết kế đủ đơn giản để thay đổi nhỏ. **Thay đổi nhỏ** giúp **CI** phản hồi nhanh và dễ chẩn đoán. **CI** cung cấp độ tin cậy để nhiều người cùng chỉnh code theo **collective ownership**. **Pair programming và coding standards** giúp kiến thức và quy ước lan khắp nhóm. **Small releases và khách hàng phản hồi sớm** giúp xác nhận liệu những thay đổi kỹ thuật ấy có tạo giá trị thật không.

Vì vậy, học XP nên hỏi: **“Thực hành này giải quyết rủi ro nào, được thực hành nào hỗ trợ và giúp việc gì tiếp theo tốt hơn?”**

## 3. Nền tảng XP: giá trị, nguyên tắc và các thực hành

### 3.1. XP hướng tới điều gì?

Extreme Programming là một phương pháp phát triển phần mềm thuộc họ Agile, nhấn mạnh chất lượng kỹ thuật, giao tiếp trực tiếp, phản hồi nhanh và khả năng thích ứng. XP chủ trương đưa những thực hành có ích như kiểm thử, review, tích hợp và nhận phản hồi vào **nhịp làm việc thường xuyên**, thay vì chỉ thực hiện một lần vào cuối giai đoạn.

Các giá trị thường được trình bày trong XP hiện đại gồm:

| Giá trị | Hành vi điển hình | Phần còn thiếu nếu chỉ làm cho có |
|---|---|---|
| **Communication — Giao tiếp** | Developers, Tester, Product Owner và người dùng làm rõ ví dụ cùng nhau | Nhiều tài liệu hoặc họp nhưng không thống nhất hành vi |
| **Simplicity — Đơn giản** | Giải pháp đủ cho nhu cầu hiện tại, tránh thiết kế dự phòng xa | Giấu nợ kỹ thuật dưới khẩu hiệu “đừng thiết kế” |
| **Feedback — Phản hồi** | Test, CI, người dùng và vận hành trả lời sớm điều đang đúng/sai | Chỉ demo ở cuối kỳ hoặc chỉ nhìn CI xanh |
| **Courage — Can đảm** | Sửa thiết kế kém, nêu rủi ro, thay đổi quyết định khi có bằng chứng | Giữ code khó thay đổi vì sợ tác giả ban đầu |
| **Respect — Tôn trọng** | Cùng chịu trách nhiệm chất lượng, tôn trọng chuyên môn và nhịp làm bền vững | Ép người khác làm thêm giờ liên tục để bù cho kế hoạch sai |

**Lưu ý về thuật ngữ:** các tài liệu và phiên bản lịch sử của XP có thể nhóm và đặt tên các thực hành khác nhau. Chẳng hạn mô tả cổ điển thường nhắc **12 practices**, còn các trình bày về sau làm rõ thêm nhiều kỹ thuật và nguyên tắc. Bài này tập trung vào **quan hệ chức năng và tác dụng hỗ trợ**, không giả định mọi đội phải triển khai nguyên một bảng kiểm cố định mới được gọi là XP.

### 3.2. Mục tiêu chung quan trọng hơn hình thức

Ba câu hỏi giúp đánh giá một thực hành XP:

1. **Phản hồi được rút ngắn ở đâu?** Từ khi hiểu sai yêu cầu, viết lỗi hoặc tích hợp không tương thích đến lúc nhóm biết chuyện.
2. **Chi phí thay đổi được giảm như thế nào?** Có thể sửa thiết kế mà không làm mất lòng tin về hành vi đã đúng không?
3. **Giá trị người dùng được kiểm chứng bằng gì?** Nhóm có phân biệt phần mềm chạy đúng với việc người dùng thực sự đạt mục tiêu không?

Một thực hành không trả lời được những câu này có thể chỉ đang được sử dụng như nghi thức.

## 4. Bản đồ các mối quan hệ hỗ trợ trong XP

### 4.1. Bốn vòng hỗ trợ điển hình

~~~mermaid
flowchart TD
    C["Nhu cầu và phản hồi khách hàng"] --> S["User story / ví dụ chấp nhận"]
    S --> A["Acceptance tests / điều kiện nghiệm thu"]
    A --> T["TDD và kiểm thử ở mức phù hợp"]
    T --> R["Refactoring an toàn"]
    R --> D["Thiết kế đơn giản, mã dễ thay đổi"]
    D --> M["Thay đổi nhỏ, dễ tích hợp"]
    M --> I["Continuous Integration"]
    I --> Q["Increment đạt chuẩn chất lượng"]
    Q --> L["Small release / thử với người dùng"]
    L --> C

    P["Pair programming / cộng tác kỹ thuật"] --> T
    P --> D
    P --> O["Collective code ownership"]
    K["Coding standards và kiến thức chung"] --> O
    O --> M
    I --> O
    Z["Sustainable pace"] --> P
    Z --> T
~~~

Các mũi tên là **quan hệ hỗ trợ thường gặp**, không phải trình tự bắt buộc mọi thay đổi phải đi đúng từng hộp. Thực tế có nhiều hướng tác động ngược lại: CI xanh tạo tự tin refactor, refactoring cải thiện testability, phản hồi khách hàng buộc nhóm sửa giả thuyết hoặc ưu tiên.

### 4.2. Ma trận “thực hành A giúp thực hành B”

| Thực hành nền | Hỗ trợ thực hành khác bằng cách nào? | Khi thiếu mắt xích đó |
|---|---|---|
| **TDD / automated tests** | Tạo phản hồi khi sửa và refactor; giúp collective ownership an toàn hơn | Người khác ngại sửa code, hồi quy khó phát hiện |
| **Refactoring liên tục** | Giữ thiết kế dễ hiểu, dễ chia story và dễ viết test tiếp | Tích tụ nợ kỹ thuật, mỗi thay đổi mất nhiều thời gian |
| **Simple design** | Giảm độ phức tạp khi pair, review và tích hợp thay đổi nhỏ | Thiết kế dự phòng lớn cản small releases |
| **Pair programming** | Review sớm, lan kiến thức, thống nhất coding standards | Kiến thức tập trung, review bị dồn cuối, lỗi thiết kế xuất hiện muộn |
| **Coding standards** | Giúp đọc/sửa code của nhau và giảm tranh luận vụn | Collective ownership thành nhiều phong cách không nhất quán |
| **Collective code ownership** | Giảm chờ một “chủ module”, hỗ trợ xử lý lỗi và refactor xuyên ranh giới | Mỗi việc chờ chuyên gia riêng, khó giữ nhịp tích hợp |
| **Continuous Integration** | Phát hiện sớm xung đột và hồi quy từ các thay đổi chung | Nhiều người sửa cùng code nhưng không có tín hiệu tin cậy |
| **Small releases** | Cho phản hồi sử dụng sớm để chọn story tiếp theo | Nhóm hoàn thành nhiều output nhưng không biết outcome |
| **Customer collaboration / acceptance tests** | Xác định hành vi có giá trị và kiểm chứng đúng nhu cầu | TDD/CI có thể xanh trên một giải pháp sai |
| **Sustainable pace** | Cho phép duy trì tập trung, review và cải tiến kỹ thuật lâu dài | Đuối sức, bỏ qua test và tạo vòng lặp sửa lỗi |

**Điểm cần nhớ:** không có thực hành nào “bảo lãnh” cho thực hành khác. Kiểm thử sai kỳ vọng vẫn cho kết quả sai; CI chỉ xanh trên phần kiểm tra đang tồn tại; pair programming thiếu tập trung vẫn có thể tạo hai người cùng hiểu nhầm.

## 5. Vòng kỹ thuật thứ nhất: TDD – refactoring – simple design

### 5.1. TDD cung cấp phản hồi hành vi nhỏ

**Test-Driven Development (TDD)** thường dùng chu trình:

1. **Red:** viết kiểm thử nhỏ diễn đạt hành vi cần có, xác nhận nó thất bại vì hành vi chưa được hỗ trợ.
2. **Green:** tạo lượng code đơn giản nhất hợp lý giúp kiểm thử đạt.
3. **Refactor:** cải thiện thiết kế bên trong, chạy lại kiểm thử để giữ hành vi đã xác định.

TDD không chỉ là “viết test trước để tăng coverage”. Lợi ích quan trọng là **làm rõ hành vi, tạo thiết kế có thể kiểm thử và rút ngắn thời gian nhận phản hồi**.

### 5.2. Refactoring giúp TDD không biến code thành đống giải pháp tạm

Ở bước Green, nhóm có thể chọn giải pháp rất đơn giản, chỉ đủ cho trường hợp đang xét. Nếu liên tục thêm tình huống mà không refactor, code sẽ có điều kiện lặp, phương thức dài, logic phụ thuộc chéo.

**Refactoring** là thay đổi cấu trúc bên trong mà không cố ý thay đổi hành vi bên ngoài. TDD và bộ kiểm thử tự động làm việc này an toàn hơn: sau khi tách code hoặc đổi tên/rút gọn một phần, test giúp phát hiện hành vi bị phá vỡ.

Quan hệ hai chiều:

- **TDD → refactoring:** kiểm thử giúp nhóm tự tin thay đổi cấu trúc.
- **Refactoring → TDD:** cấu trúc rõ làm unit test dễ viết, dễ hiểu và ít phải thiết lập phức tạp.

Nếu test gắn chặt vào tên phương thức nội bộ, thứ tự gọi mock hoặc các chi tiết cài đặt không mang ý nghĩa nghiệp vụ, refactoring có thể làm hỏng nhiều test **dù hành vi bên ngoài không đổi**. Khi đó cần xem lại thiết kế test, không kết luận refactoring là có hại.

### 5.3. Simple design tạo điều kiện cho thay đổi nhỏ

**Thiết kế đơn giản (simple design)** không có nghĩa code cẩu thả hoặc không được suy nghĩ về kiến trúc. Nó hướng tới **giải pháp dễ hiểu nhất đáp ứng yêu cầu hiện tại và các ràng buộc đã biết**, không xây trước hệ thống phức tạp chỉ vì “có thể tương lai sẽ cần”.

Một thiết kế đủ đơn giản giúp:

- Dễ chia thay đổi thành **lát cắt nhỏ có thể kiểm chứng**.
- Test chạy nhanh và lỗi được khoanh vùng tốt hơn.
- Pair programming và review dễ đi vào hành vi quan trọng.
- CI có ít thay đổi mỗi lần, giảm khó khăn tìm nguyên nhân khi pipeline đỏ.

Nhưng “đơn giản” phải tính cả **bảo mật, dữ liệu, vận hành và khả năng phục hồi**. Bỏ một kiểm soát quan trọng để giảm số dòng code không phải thiết kế đơn giản theo tinh thần chuyên nghiệp.

### 5.4. Ví dụ Red–Green–Refactor cho việc lưu tiến độ

**Nhu cầu:** giao diện không được báo “Đã lưu” khi hệ thống chưa nhận xác nhận hợp lệ từ nơi lưu dữ liệu.

Ví dụ pseudo-Java dưới đây minh họa ý tưởng, **không phải ứng dụng hoàn chỉnh hoặc API chuẩn**:

~~~java
enum SaveStatus {
    CONFIRMED, FAILED
}

interface ProgressRepository {
    boolean save(String userId, int lessonId, int position);
}

final class ProgressService {
    private final ProgressRepository repository;

    ProgressService(ProgressRepository repository) {
        this.repository = repository;
    }

    SaveStatus saveProgress(String userId, int lessonId, int position) {
        boolean confirmed = repository.save(userId, lessonId, position);
        return confirmed ? SaveStatus.CONFIRMED : SaveStatus.FAILED;
    }
}
~~~

Một kiểm thử minh họa:

~~~java
// Pseudocode dùng cú pháp JUnit 5; giả định có test double tương ứng.
@Test
void doesNotConfirmSaveWhenRepositoryFails() {
    ProgressRepository failingRepository =
        (userId, lessonId, position) -> false;
    ProgressService service = new ProgressService(failingRepository);

    SaveStatus result = service.saveProgress("learner-1", 10, 35);

    assertEquals(SaveStatus.FAILED, result);
}
~~~

**Giới hạn của ví dụ:** trong hệ thống thật, thao tác lưu có thể bất đồng bộ, kết quả chưa xác định khi timeout, dữ liệu tranh chấp hoặc yêu cầu về quyền truy cập. Không suy ra từ mã trên rằng chỉ cần một boolean là đủ an toàn. Cần làm rõ **các trạng thái nghiệp vụ và hợp đồng API**, rồi bổ sung integration/contract tests theo rủi ro.

Chu trình thực tế có thể là:

~~~text
Nhu cầu: Không báo lưu thành công khi chưa có xác nhận.
    ↓
RED: Test mô tả tình huống repository không xác nhận.
    ↓
GREEN: Chỉ trả CONFIRMED khi có kết quả lưu thành công.
    ↓
REFACTOR: Làm rõ ranh giới xử lý trạng thái và phụ thuộc.
    ↓
CI: Chạy lại test, kiểm tra tương thích với phần tích hợp.
    ↓
Acceptance test: Kiểm tra UI không hiển thị "Đã lưu" sai.
    ↓
Increment và phản hồi: Người học có tiếp tục học tin cậy hơn?
~~~

Như vậy **TDD không tự thay thế acceptance tests, CI hay phản hồi người dùng**. Nó giải quyết một lớp phản hồi; những lớp khác xác nhận hệ thống và giá trị.

### 5.5. Các tình huống làm đứt vòng TDD–refactoring

| Dấu hiệu | Mắt xích yếu | Cách cải thiện |
|---|---|---|
| Test viết sau cùng chỉ để đủ coverage | Thiếu phản hồi thiết kế sớm | Chọn một quy tắc nhỏ, thử Red–Green–Refactor có chủ đích |
| Mỗi lần refactor phải sửa hàng chục mock | Test bám chi tiết triển khai | Ưu tiên kiểm tra hành vi và ranh giới ổn định |
| Test quá chậm nên Developers không chạy | Phản hồi không đủ nhanh | Phân tầng kiểm tra; bộ test nhanh cho vòng phát triển |
| Code chứa nhiều điều kiện lặp sau nhiều story | Thiếu refactoring liên tục | Dành thời gian cải thiện khi vẫn có test bảo vệ hành vi |
| “YAGNI” bị dùng để bỏ bảo mật | Hiểu sai simple design | Tính các yêu cầu chất lượng và rủi ro hiện tại vào thiết kế |

## 6. Vòng kỹ thuật thứ hai: pair programming – collective ownership – coding standards

### 6.1. Pair programming là cộng tác, không chỉ ngồi chung bàn

**Pair programming** là hai người cùng làm việc trên một thay đổi ở một thời điểm, liên tục trao đổi về hành vi, thiết kế, kiểm thử và rủi ro. Một cách tổ chức quen thuộc là người thao tác (*driver*) và người quan sát, đặt câu hỏi (*navigator*) luân phiên.

Pairing có thể giúp:

- Phát hiện hiểu nhầm về yêu cầu ngay khi thiết kế.
- Đưa review vào **quá trình tạo code**, thay vì chờ một đợt review cuối.
- Chia sẻ kiến thức về module và những quy ước khó viết hết thành tài liệu.
- Giảm phụ thuộc khi người hiểu một phần hệ thống vắng mặt.
- Cải thiện năng lực sử dụng TDD, refactoring và CI nhờ cùng xem phản hồi.

Không phải lúc nào cũng cần hai người cùng code từng dòng. Một phiên pairing hiệu quả có mục tiêu rõ, thời lượng phù hợp, luân phiên vai trò và tôn trọng khả năng tập trung của cả hai.

### 6.2. Collective code ownership là gì?

**Collective code ownership** nghĩa là mọi thành viên có năng lực trong nhóm có thể cải thiện phần mã cần thiết để giao một thay đổi, thay vì bị ngăn bởi một “lãnh địa code” tuyệt đối của cá nhân.

Nhưng quyền sửa rộng **không đồng nghĩa** được bỏ qua:

- Chính sách review, kiểm soát truy cập và phân quyền của tổ chức.
- Tiêu chuẩn bảo mật hoặc quy trình phê duyệt đặc biệt cho thành phần nhạy cảm.
- Kiểm thử, CI và Definition of Done áp dụng.
- Việc trao đổi với người có kiến thức cần thiết trước thay đổi rủi ro cao.

Trong sản phẩm nhiều nhóm, **collective ownership cần được thiết kế phù hợp phạm vi trách nhiệm thực tế**, không phải mọi tài khoản trên toàn công ty đều có quyền sửa production.

### 6.3. Pairing làm ownership thực chất hơn

Nếu một module chỉ có một người hiểu, câu “mọi người đều có quyền sửa” chỉ đúng trên giấy. Những người khác vẫn sợ tạo lỗi.

Pairing và luân phiên cộng tác giúp **chuyển giao tri thức trong khi tạo sản phẩm thật**, nên:

- Người thứ hai hiểu được lý do thiết kế và các giới hạn.
- Nhóm có thêm người biết chạy test, chẩn đoán lỗi và cải thiện mã.
- Việc xử lý sự cố hoặc refactor xuyên module không phải chờ đúng một người.

Ngược lại, collective ownership tạo điều kiện để kiến thức thu được qua pairing được **áp dụng**, thay vì người mới học xong vẫn không được động vào mã.

### 6.4. Coding standards giảm chi phí phối hợp

Quy ước mã giúp nhóm đọc và thay đổi code nhất quán:

- Định dạng và tên gọi đủ rõ.
- Cách tổ chức test, log, xử lý lỗi và cấu trúc package/module.
- Nguyên tắc bảo vệ dữ liệu, quản lý secret và cấu hình.
- Các quy tắc có thể tự động hóa bằng formatter/linter khi phù hợp.

Khi nhiều người cùng sửa code, quy ước giúp review tập trung vào **hành vi và thiết kế**, không mất thời gian tranh luận lại hàng ngày về khoảng trắng hay vị trí dấu ngoặc.

Không nên biến coding standards thành bộ luật cấm mọi ý tưởng mới. Nhóm có thể cải tiến quy ước khi có bằng chứng tốt hơn, rồi áp dụng nhất quán.

### 6.5. Mối quan hệ bốn chiều với CI

~~~text
Pair programming
   → lan kiến thức và phát hiện sai sót sớm
       → collective code ownership khả thi hơn
           → nhiều thành viên có thể sửa và cải thiện module cần thiết
               → coding standards giảm ma sát khi cùng sửa
                   → CI xác nhận các thay đổi vẫn tích hợp và chạy đúng
                       → nhóm tin tưởng hơn vào collective ownership
~~~

**Nếu bỏ CI hoặc test đáng tin:** nhiều người chỉnh sửa cùng vùng mã có thể tạo xung đột và hồi quy khó phát hiện.

**Nếu bỏ chia sẻ kiến thức:** có CI nhưng vẫn chỉ một người biết nguyên nhân những test khó hoặc có thể sửa cấu hình.

**Nếu bỏ quy ước:** code trở nên khó đọc theo thời gian, mọi thay đổi phát sinh tranh luận vụn và review tắc.

Vì vậy, các thực hành hỗ trợ nhau nhưng không tự đủ chỉ vì được bật trong một công cụ.

## 7. Vòng kỹ thuật thứ ba: CI – thay đổi nhỏ – phát hành nhỏ

### 7.1. Continuous Integration là vòng phản hồi chung

**Continuous Integration (CI)** nhấn mạnh tích hợp mã thường xuyên vào một nhánh chung và tự động kiểm tra đủ nhanh, đủ tin cậy để phát hiện xung đột hoặc lỗi khi chúng còn nhỏ.

Một CI có ích thường có:

- Các thay đổi nhỏ, tích hợp thường xuyên thay vì nhánh kéo dài nhiều tuần.
- Build và kiểm tra nhanh cho các lỗi thường gặp.
- Kiểm thử ở những mức phù hợp với rủi ro.
- Tín hiệu lỗi **nhìn thấy được**, có người và cách khôi phục trạng thái ổn.
- Chính sách rõ về khi nào thay đổi đủ điều kiện vào nhánh chung.

CI không đồng nghĩa với **Continuous Delivery** hoặc **Continuous Deployment**. CI là năng lực tích hợp và phản hồi về code; phát hành tới người dùng có thể cần bước kiểm chứng, chấp thuận và kiểm soát khác theo sản phẩm.

### 7.2. Tại sao CI cần thay đổi nhỏ?

Giả sử hai tình huống:

| Tình huống | Khi pipeline đỏ | Khả năng phản hồi |
|---|---|---|
| Thay đổi nhỏ, mới có một quy tắc lưu tiến độ | Dễ khoanh vùng các dòng và test liên quan | Sửa/rollback tương đối nhanh |
| Nhánh tích hợp sau ba tuần, thay đổi nhiều API và cấu trúc dữ liệu | Khó biết nguyên nhân do phần nào hay tương tác nào | Tốn thời gian điều tra, xung đột và làm lại |

**Small changes → CI hữu ích hơn**, còn **CI xanh → nhóm tự tin tạo small changes tiếp**. Đây là một vòng củng cố.

Không đồng nghĩa mọi commit phải là một tính năng hoàn chỉnh. Có thể dùng các kỹ thuật phát triển gia tăng, cấu hình an toàn hoặc feature flag để tích hợp từng phần **mà không phơi bày hành vi chưa sẵn sàng cho người dùng**. Feature flag cũng cần được kiểm soát, kiểm thử hai trạng thái liên quan và dọn dẹp khi hết mục đích.

### 7.3. Small releases mang phản hồi ngoài codebase trở lại

**Small releases** hướng đến giao những phần nhỏ có giá trị và đủ chất lượng thường xuyên để người dùng hoặc stakeholder kiểm chứng.

Một Increment có thể đạt DoD nhưng chưa được triển khai cho mọi người; một bản triển khai kỹ thuật có thể chưa được bật chức năng cho người dùng. Do đó cần phân biệt:

- **Tích hợp:** code mới cùng hoạt động trong hệ thống chung.
- **Increment đạt DoD:** phần sản phẩm tích hợp đáp ứng chuẩn chất lượng áp dụng.
- **Phát hành/triển khai:** cung cấp thay đổi cho người dùng hoặc môi trường mục tiêu theo chính sách.
- **Outcome:** hành vi hoặc kết quả của người dùng thay đổi thế nào sau khi họ sử dụng.

Điểm quan trọng là **thời gian từ giả thuyết tới bằng chứng** phải đủ ngắn để nhóm còn cơ hội thay đổi quyết định.

### 7.4. Chất lượng phản hồi quan trọng hơn số lượt build

Một pipeline chạy 100 lần/ngày nhưng gần như không kiểm tra hành vi quan trọng có thể vẫn cho cảm giác an toàn giả. Nhóm cần cân bằng:

| Lớp kiểm tra | Vai trò | Giới hạn |
|---|---|---|
| Static checks/type/lint | Phát hiện sai sót cơ bản sớm | Không chứng minh nghiệp vụ đúng |
| Unit/component tests | Kiểm tra quy tắc và thành phần nhỏ | Không chứng minh mọi phần tích hợp |
| Contract/integration tests | Kiểm tra ranh giới dịch vụ và dữ liệu | Có thể bỏ sót trải nghiệm giao diện |
| Acceptance/end-to-end tests chọn lọc | Kiểm tra hành trình người dùng quan trọng | Thường tốn kém, có thể giòn nếu dùng quá mức |
| Quan sát sau triển khai | Phát hiện tình huống thực tế và outcome | Không thay thế kiểm tra rủi ro trước phát hành |

**Phản hồi kỹ thuật và phản hồi sản phẩm khác nhau.** Cần cả hai để tránh xây một hệ thống chạy ổn định nhưng giải quyết sai nhu cầu.

## 8. Vòng sản phẩm: customer collaboration – stories – acceptance tests – small releases

### 8.1. Khách hàng sẵn sàng giải thích và phản hồi

XP cổ điển nhấn mạnh **on-site customer**: có đại diện hiểu nhu cầu, sẵn sàng làm rõ ưu tiên và trả lời các câu hỏi của đội phát triển. Trong môi trường hiện đại, người này không nhất thiết phải ngồi vật lý cùng phòng mọi ngày, nhưng đội cần **đường phản hồi đủ nhanh, đáng tin và có thẩm quyền phù hợp**.

Nếu khách hàng không có thời gian:

- Đặt câu hỏi cụ thể với ví dụ.
- Thỏa thuận thời điểm nhận phản hồi và nơi ghi quyết định.
- Dùng prototype hoặc lát cắt nhỏ để giảm tranh luận trừu tượng.
- Ghi rõ điều đã biết và điều chưa biết, tránh tự đoán chính sách nghiệp vụ có rủi ro cao.

**Product Owner** trong Scrum có thể là đầu mối rất quan trọng về giá trị và thứ tự backlog, nhưng không nên tự mặc định một người biết hết mọi chi tiết pháp lý, bảo mật hoặc hành vi người dùng. Developers vẫn cần cộng tác với người dùng và chuyên gia khi phù hợp.

### 8.2. User stories đưa giá trị về phạm vi có thể trao đổi

Ví dụ:

> **Là** người học đang học dở, **tôi muốn** biết tiến độ đã được lưu thành công **để** có thể yên tâm rời bài và tiếp tục học sau.

Story tạo điều kiện trao đổi về người dùng và lợi ích, không phải bản đặc tả hoàn chỉnh chỉ vì đã có mẫu “Là... tôi muốn... để...”.

Một story tốt thường:

- Đủ nhỏ để giao và kiểm chứng trong một vòng ngắn.
- Độc lập vừa đủ để tránh chờ nhiều hệ thống chưa cần.
- Có giá trị người dùng hoặc mục đích giảm rủi ro rõ.
- Có ví dụ kiểm chứng, không chỉ tên giao diện.

Những đặc tính như “INVEST” là hướng dẫn có thể tham khảo; **Scrum không bắt buộc mọi PBI đều là user story**.

### 8.3. Acceptance tests giúp nối ngôn ngữ nghiệp vụ với code

**Acceptance tests** kiểm chứng những kịch bản có ý nghĩa với người dùng hoặc nghiệp vụ. Chúng bổ trợ TDD ở mức quy tắc nhỏ.

~~~gherkin
Tính năng: Người học nhận thông tin lưu tiến độ đáng tin

Kịch bản: Lưu thành công
  Cho trước người học đang ở bài hợp lệ và có quyền học
  Khi hệ thống xác nhận tiến độ đã được lưu
  Thì giao diện thể hiện trạng thái đã lưu phù hợp
  Và tiến độ có thể được truy vấn lại theo quy tắc sản phẩm

Kịch bản: Dịch vụ không xác nhận lưu
  Cho trước người học có thay đổi tiến độ chưa được xác nhận
  Khi dịch vụ lưu không trả xác nhận thành công
  Thì giao diện không khẳng định đã lưu thành công
  Và người học nhận trạng thái hoặc hướng dẫn xử lý phù hợp

Kịch bản: Người dùng gửi thao tác lưu lặp lại
  Cho trước một yêu cầu lưu được gửi lại do gián đoạn mạng
  Khi hệ thống xử lý các yêu cầu tương đương
  Thì tiến độ không bị lùi hoặc ghi sai trái với quy tắc đồng bộ
  Và hệ thống phản hồi nhất quán với trạng thái dữ liệu thực

Kịch bản: Tài khoản không đủ quyền
  Cho trước người học không có quyền đọc tiến độ của người khác
  Khi tài khoản đó yêu cầu dữ liệu không thuộc quyền
  Thì hệ thống từ chối truy cập theo chính sách
  Và không tiết lộ nội dung tiến độ được bảo vệ
~~~

Đây là các **tiêu chí minh họa**, chưa xác định đầy đủ cách đồng bộ nhiều thiết bị hoặc trạng thái timeout của sản phẩm thật. Cần cùng Product Owner và chuyên gia xác nhận những chính sách còn thiếu.

### 8.4. Vòng hai chiều: story và release

~~~text
Người dùng gặp vấn đề
  → nhóm làm rõ story, ví dụ chấp nhận
  → TDD/thiết kế/test/integration xây lát cắt nhỏ
  → Increment đạt chuẩn chất lượng
  → phát hành hoặc thử trong phạm vi thích hợp
  → người dùng phản hồi, dữ liệu cho thấy hành vi thực
  → điều chỉnh story và thứ tự ưu tiên tiếp theo
~~~

**Acceptance tests đúng không tự chứng minh outcome đạt.** Một luồng có thể mở bài thành công nhưng người học vẫn không hoàn thành bài vì nội dung khó hiểu. Small releases giúp nhóm **kiểm tra giả thuyết sản phẩm**, còn kiểm thử kỹ thuật giúp bảo vệ phần mềm khi thay đổi hướng.

### 8.5. Planning game và phạm vi thích ứng

Trong các mô tả XP cổ điển, **planning game** tạo cách trao đổi giữa người hiểu giá trị kinh doanh và Developers về nhu cầu, chi phí, lựa chọn phạm vi và kế hoạch trong tương lai gần.

Cách tổ chức có thể khác nhau:

| Góc nhìn | Câu hỏi chính |
|---|---|
| **Sản phẩm/khách hàng** | “Giá trị nào cần sớm nhất? Điều gì có thể hoãn để học trước?” |
| **Developers** | “Rủi ro, phụ thuộc và độ phức tạp thực tế ra sao? Có thể chia lát cắt không?” |
| **Cùng nhau** | “Với năng lực, chất lượng và bằng chứng hiện có, phần nào đáng giao trong vòng tiếp?” |

**Không biến ước lượng thành lời hứa tuyệt đối.** Lập kế hoạch ngắn hạn có giá trị vì nó cho phép đổi hướng sau khi nhận phản hồi, chứ không vì mọi dự báo luôn đúng.

## 9. Vòng bền vững: sustainable pace làm các thực hành khác tồn tại được

XP cũng nhấn mạnh **nhịp làm việc bền vững**. Nếu nhóm thường xuyên làm thêm giờ kéo dài để hoàn thành cam kết quá lớn, những hành động bị cắt đầu tiên thường là kiểm thử, refactoring, review kỹ lưỡng và trao đổi về yêu cầu.

Một vòng đi xuống có thể hình thành:

~~~text
Quá tải / deadline không khả thi
  → bỏ qua test, refactoring và review
  → hồi quy, xung đột tích hợp, làm lại
  → dự báo trễ hơn
  → tăng áp lực và tiếp tục cắt chất lượng
~~~

Vòng hỗ trợ ngược lại:

~~~text
Phạm vi nhỏ, ưu tiên minh bạch
  → phản hồi sớm từ CI và người dùng
  → ít làm lại, mã dễ thay đổi hơn
  → kế hoạch dựa trên năng lực thật
  → còn sức để giữ test, review, pairing và cải tiến
~~~

**Sustainable pace không đồng nghĩa nhóm làm chậm hoặc thiếu trách nhiệm.** Nó hỗ trợ duy trì chất lượng và khả năng dự báo lâu dài. Trong tình huống sự cố nghiêm trọng, vẫn có thể cần ứng cứu khẩn; nhưng ứng cứu không nên trở thành mô hình vận hành mặc định cho mọi tuần.

### 9.1. Mối liên hệ với Kanban và WIP

Hạn chế **Work in Progress (WIP)** giúp tránh mở nhiều hạng mục đồng thời khiến Developer chuyển ngữ cảnh liên tục. Khi một PBI đang chờ review hoặc test, nhóm có thể hỗ trợ hoàn tất trước khi kéo thêm.

Những chỉ số như **throughput, cycle time, work item age và WIP** cho thấy dòng công việc, nhưng không đo trực tiếp giá trị sản phẩm hay hiệu suất cá nhân. Dùng chúng để tìm điểm nghẽn và giảm thời gian chờ, không để ép tất cả người cùng lúc phải bận 100%.

## 10. Nếu một thực hành bị thiếu thì điều gì xảy ra?

### 10.1. Bảng phân tích đứt gãy các vòng hỗ trợ

| Chỉ áp dụng... | Nhưng thiếu... | Rủi ro | Cách khôi phục liên kết |
|---|---|---|---|
| **TDD** | Refactoring và kiểm thử ở mức tích hợp | Nhiều unit test nhưng thiết kế khó đổi, lỗi qua ranh giới vẫn lọt | Refactor đều, thêm contract/integration tests theo rủi ro |
| **Refactoring** | Bộ kiểm thử đáng tin | Khó biết có phá hành vi không | Thêm test mô tả hành vi trước thay đổi rủi ro |
| **Pair programming** | Mục tiêu, luân phiên và kiến thức chung | Hai người cùng tập trung sai vấn đề, không lan kỹ năng | Làm rõ story, chuyển vai, chia sẻ bài học |
| **Collective ownership** | CI, standards và review phù hợp | Nhiều người sửa nhưng xung đột/hồi quy tăng | Giảm kích thước thay đổi, CI và quy ước rõ |
| **CI** | Tích hợp thường xuyên và test đáng tin | Pipeline chạy nhưng không chặn sai lệch có ý nghĩa | Làm test hữu ích, rút ngắn vòng tích hợp |
| **Small releases** | Definition of Done hoặc tiêu chí chấp nhận | Giao nhanh nhưng sai hoặc không an toàn | Bảo vệ chất lượng và kiểm chứng hành vi cốt lõi |
| **Acceptance tests** | Phản hồi người dùng thật | Hệ thống đúng kịch bản đã viết nhưng sai nhu cầu | Quan sát hành vi sản phẩm và điều chỉnh giả thuyết |
| **Customer collaboration** | Developers tham gia trao đổi và chia lát cắt | Ý kiến thành danh sách yêu cầu lớn, không được kiểm chứng | Cùng làm rõ ví dụ, độ phức tạp và giá trị |
| **Sustainable pace** | Ưu tiên minh bạch và giảm WIP | Nhịp làm việc vẫn bị phá bởi việc chen ngang | Kiểm soát công việc mở, quản lý đánh đổi |

### 10.2. Không diễn giải thành “phải dùng tất cả hoặc không dùng gì”

Các thực hành hỗ trợ nhau **không có nghĩa mọi nhóm phải áp dụng tất cả cùng lúc**, càng không phải mọi thay đổi đều bắt buộc pairing, TDD, end-to-end test và phát hành ngay trong một ngày.

Hãy xem xét:

1. **Rủi ro hiện tại:** điều gì đang làm nhóm chậm nhận phản hồi hoặc khó thay đổi?
2. **Điều kiện hỗ trợ:** thực hành nào còn thiếu để giải pháp được chọn có hiệu quả?
3. **Phạm vi thử:** có thể thử một nhóm story, module hoặc vòng ngắn trước không?
4. **Tín hiệu bảo vệ:** có giảm lỗi, giữ năng lực giao Increment và cải thiện trải nghiệm không?

**XP là một hệ thống học hỏi có tính bổ trợ**, nhưng lựa chọn thực hành cần dựa trên bối cảnh, không dựa trên số ô được đánh dấu trong checklist.

## 11. Tình huống xuyên suốt: cải thiện chức năng lưu tiến độ học

### 11.1. Product Goal và rủi ro ban đầu

Một Scrum Team đang xây nền tảng học trực tuyến có Product Goal:

> “Người học có thể tiếp tục bài học ở thời điểm đã dừng, với trạng thái lưu tiến độ đáng tin trên các thiết bị được hỗ trợ.”

Nhóm nhận phản hồi:

- Khi mạng yếu, UI đôi khi hiện “Đã lưu” mặc dù dữ liệu chưa ghi thành công.
- Lỗi hồi quy xuất hiện mỗi lần chỉnh sửa logic lưu.
- Mỗi khi cần sửa module lưu tiến độ, nhóm phải chờ một Developer có kinh nghiệm.
- Tích hợp UI–API–dữ liệu thường diễn ra cuối Sprint.

Nếu chỉ thêm test riêng lẻ hoặc chỉ thêm người cho review, có thể chưa giải quyết được toàn bộ nguyên nhân.

### 11.2. Làm rõ bài toán sản phẩm trước khi code

Product Owner, Developers và người có chuyên môn kiểm thử cùng xem ví dụ:

> “Người học chỉ được nhận thông tin đã lưu khi dịch vụ xác nhận; khi chưa có kết quả hoặc có lỗi, giao diện phải phản ánh đúng trạng thái. Khi mở lại trên thiết bị khác, dữ liệu phải tuân theo quy tắc đồng bộ đã thống nhất.”

Nhóm xác định cần làm rõ thêm:

- Cách xử lý timeout và trạng thái chưa chắc thành công/thất bại.
- Chính sách thử lại, dữ liệu lặp và xung đột hai thiết bị.
- Quyền truy cập dữ liệu tiến độ và những gì không được ghi vào log.
- Phạm vi thiết bị/điều kiện mạng được hỗ trợ trong lát cắt đầu.

Thông tin được chuyển vào acceptance criteria và thứ tự Product Backlog, không tự giả định tất cả rủi ro đã rõ.

### 11.3. Tách lát cắt đầu tiên có thể kiểm chứng

Thay vì thiết kế ngay hệ thống offline đa thiết bị hoàn chỉnh, nhóm chọn:

> “Trong một phiên học có kết nối, giao diện chỉ hiển thị trạng thái đã lưu sau khi API có xác nhận hợp lệ; khi lưu thất bại, hiển thị trạng thái không thành công và bước tiếp theo phù hợp.”

Lát cắt đi xuyên **UI → API → lưu dữ liệu → kiểm thử**, có thể tích hợp và kiểm chứng. Các tình huống đồng bộ phức tạp hơn vẫn được ghi nhận như công việc tiếp theo nếu cần và có bằng chứng.

### 11.4. Các thực hành XP hỗ trợ nhau trong một ngày làm việc

| Thời điểm | Thực hành áp dụng | Liên hệ hỗ trợ |
|---|---|---|
| Trước khi viết code | Trao đổi ngắn với Product Owner và Tester về ví dụ | Tạo acceptance tests có nghĩa, tránh unit test sai mục tiêu |
| Bắt đầu xử lý trạng thái lưu | Pair programming và TDD cho quy tắc phản hồi | Pairing hỗ trợ thiết kế test, chia sẻ kiến thức |
| Sau khi test xanh | Refactoring để tách trạng thái lưu khỏi UI | Test bảo vệ hành vi; thiết kế đơn giản hơn cho story tiếp |
| Thay đổi nhỏ hoàn tất | Commit và tích hợp thường xuyên | CI phát hiện xung đột/hồi quy sớm |
| Có lỗi contract với UI | Cùng làm rõ, sửa API/test | Collective ownership giúp người phù hợp xử lý ngay |
| Một lát cắt đạt DoD | Kiểm thử chấp nhận và quan sát trong môi trường thử | Xác định phần thực sự là Increment, không chỉ code riêng lẻ |
| Sau khi người học thử | Thu thập phản hồi và lỗi thực tế | Small release cung cấp bằng chứng cho ưu tiên tiếp theo |

### 11.5. CI đỏ: phát hiện sai lệch và phối hợp thay vì đổ lỗi

Giả sử hai người vừa refactor phần API, CI báo integration test thất bại khi UI nhận trạng thái timeout.

Nhóm không để build đỏ kéo dài rồi chuyển sang tính năng khác. Họ:

1. Làm rõ failure và kiểm tra xem test có phản ánh hợp đồng thật.
2. Sửa hoặc đảo thay đổi chưa an toàn theo chính sách tích hợp.
3. Bổ sung ví dụ timeout vào acceptance/contract tests khi cần.
4. Luân phiên người tìm hiểu lỗi để tránh một người thành điểm tắc duy nhất.
5. Chỉ tiếp tục tích hợp khi tín hiệu chất lượng đáng tin được khôi phục.

**TDD + CI + collective ownership + pairing** cùng phát huy tác dụng: lỗi được phát hiện sớm, nhiều người đủ hiểu biết để sửa, thay đổi vẫn nhỏ và có thể truy tìm.

### 11.6. Kiểm tra Increment và phản hồi người dùng

Sau khi lát cắt đầu đạt **Definition of Done**, Scrum Team có thể đưa vào môi trường dùng thử có kiểm soát. Giả sử họ theo dõi:

| Tín hiệu | Câu hỏi |
|---|---|
| Tỷ lệ thao tác lưu không được xác nhận | Lỗi lưu có giảm không? |
| Số báo cáo mất tiến độ được xác minh | Người học có còn mất công sức học không? |
| Thời gian từ thay đổi code tới phản hồi CI | Phản hồi kỹ thuật có đủ sớm không? |
| Lỗi hồi quy sau khi sửa lưu tiến độ | Lưới kiểm thử có bảo vệ thay đổi không? |
| Work item age và cycle time của PBI liên quan | Việc có bị chờ review hoặc tích hợp quá lâu không? |
| Tỷ lệ người học tiếp tục bài và hoàn thành bài | Cải tiến có giúp Product Goal không? |

Không dùng một chỉ số duy nhất như “test coverage tăng” để khẳng định người học đã có trải nghiệm tốt hơn.

### 11.7. Ví dụ số liệu giả định và cách đọc

Giả sử hai giai đoạn quan sát có dữ liệu **hoàn toàn minh họa**:

| Chỉ báo | Giai đoạn đầu | Giai đoạn sau | Nhận định thận trọng |
|---|---:|---:|---|
| Số lỗi mất tiến độ được xác minh | 16 | 6 | Có tín hiệu cải thiện, cần xét lượng người dùng và thời gian |
| Lỗi hồi quy liên quan sau phát hành | 7 | 3 | Có thể có ích từ kiểm thử tốt hơn, chưa chứng minh nguyên nhân |
| Cycle time trung vị của PBI lưu tiến độ | 9 ngày | 6 ngày | Cần xét loại việc, số mẫu và việc chưa Done |
| Tỷ lệ người học hoàn thành bài đầu | 27% | 29% | Outcome tăng nhẹ, có thể do nhiều yếu tố |

Không đủ căn cứ kết luận “XP làm tăng hoàn thành bài 2 điểm phần trăm” chỉ từ bảng này. Cần kiểm tra nguồn dữ liệu, người dùng, phạm vi thay đổi, tính đại diện, biến động và những cải tiến diễn ra đồng thời.

### 11.8. Học tiếp thay vì tuyên bố xong mọi việc

Nếu người học vẫn bỏ dở ở giữa bài dù trạng thái lưu đúng, nhóm có thể nhận ra **vấn đề nội dung hoặc trải nghiệm học** mới quan trọng. Product Owner sắp lại thứ tự backlog dựa trên dữ liệu; Developers vẫn có khả năng điều chỉnh giải pháp nhanh nhờ mã được kiểm thử và tích hợp thường xuyên.

Đó là quan hệ cuối cùng trong hệ XP: **kỹ thuật tốt làm giảm chi phí thay đổi, còn phản hồi sản phẩm quyết định thay đổi theo hướng nào**.

## 12. Phối hợp XP với Scrum và Kanban

### 12.1. Scrum cung cấp khung quản lý mục tiêu và kiểm tra

Scrum định nghĩa accountabilities, sự kiện và artifacts với các cam kết tương ứng:

- **Product Backlog → Product Goal:** minh bạch hướng cải thiện sản phẩm.
- **Sprint Backlog → Sprint Goal:** mục tiêu và kế hoạch cho Sprint hiện tại.
- **Increment → Definition of Done:** chuẩn chất lượng cho phần sản phẩm hoàn thành.

XP **không thay thế** các trách nhiệm đó. Nó có thể bổ sung cách thực hiện cụ thể để Developers tạo Increment đáng tin: TDD, pairing, CI, refactoring và phát hành nhỏ khi phù hợp.

Ví dụ, trong Sprint Planning, Scrum Team chọn Sprint Goal liên quan tới lưu tiến độ; XP giúp Developers **tạo các lát cắt kỹ thuật** có phản hồi thường xuyên; Sprint Review kiểm tra Increment và điều vừa học.

**Scrum Guide không bắt buộc mọi Scrum Team dùng TDD hoặc pair programming.** Ngược lại, một đội áp dụng XP không nhất thiết phải dùng các sự kiện Scrum nếu họ không chọn framework này. Chúng có thể kết hợp vì phục vụ những khía cạnh bổ trợ.

### 12.2. Kanban hỗ trợ nhìn dòng công việc

Kanban cung cấp cách **định nghĩa workflow, kiểm soát WIP và dùng dữ liệu luồng** để cải thiện khả năng giao việc.

Khi một đội thực hành XP:

- **WIP limit** giúp tránh mở quá nhiều story khiến pairing, review và CI bị dồn.
- **Work item age** chỉ ra story nào bị kẹt vì phụ thuộc hay test không ổn.
- **Cycle time** phản ánh thời gian từ bắt đầu tới hoàn thành của công việc cùng loại.
- **Throughput** phản ánh số hạng mục hoàn thành trong một giai đoạn.

Những phép đo này chỉ có ý nghĩa khi **định nghĩa Done rõ và nhất quán**. Đẩy ticket chưa đạt DoD thành Done để tăng throughput làm hỏng dữ liệu và vòng phản hồi.

### 12.3. Lean tạo góc nhìn về chất lượng và lãng phí

Lean nhắc nhóm tránh tích trữ công việc dở, phát hiện sai lệch tại nguồn khi có thể và giảm làm lại. XP cung cấp nhiều kỹ thuật thực tiễn để thực hiện những mục tiêu ấy trong phát triển phần mềm.

Không nên gọi mọi thực hành “Lean”, “Kanban”, “Scrum” và “XP” là tương đương. Chúng có lịch sử và trọng tâm khác nhau; kết hợp cần phục vụ **mục tiêu sản phẩm và vấn đề thực tế**, không phải cố dùng đủ nhãn.

## 13. Bắt đầu áp dụng XP như một hệ thống bổ trợ

### 13.1. Chọn vấn đề trước khi chọn thực hành

Một nhóm chưa áp dụng đầy đủ XP có thể bắt đầu bằng bảng sau:

| Tín hiệu hiện tại | Vòng hỗ trợ cần xem | Thử nghiệm ban đầu |
|---|---|---|
| Refactor thường gây lỗi hồi quy | Test → refactoring → simple design | Viết test hành vi cho một module rủi ro trước khi refactor |
| Chỉ một người dám sửa code quan trọng | Pairing → shared knowledge → collective ownership | Pair luân phiên ở một story có mục tiêu chia sẻ kiến thức |
| Lỗi tích hợp phát hiện cuối Sprint | Small changes → CI → integration tests | Tích hợp một lát cắt nhỏ thường xuyên, kiểm tra contract quan trọng |
| Test coverage cao nhưng người dùng không hài lòng | Customer examples → acceptance tests → small releases | Tổ chức phiên làm rõ và thử hành trình với người dùng thật |
| Review và QA luôn bị nghẽn | WIP control → finish work → CI | Giảm việc đang mở, hỗ trợ việc gần Done |
| Nhóm kiệt sức sau mỗi đợt release | Sustainable pace → chất lượng lâu dài | Làm rõ năng lực, giảm phạm vi và theo dõi làm lại |

Không nhất thiết triển khai sáu thử nghiệm đồng thời. Khi quá nhiều thứ thay đổi, khó biết điều gì tạo tác dụng hoặc điểm tắc mới.

### 13.2. Lộ trình thực hành minh họa theo bốn vòng ngắn

| Vòng | Trọng tâm | Kết quả muốn quan sát |
|---|---|---|
| **1. Minh bạch** | Chọn một luồng quan trọng, làm rõ DoD, acceptance criteria và lỗi phát hiện muộn | Có hiểu biết chung về điểm đau và trạng thái Done |
| **2. Phản hồi code** | TDD cho quy tắc rủi ro, refactor được test bảo vệ, CI cho thay đổi nhỏ | Lỗi được phát hiện sớm, ít sợ sửa mã |
| **3. Cộng tác và tích hợp** | Pair luân phiên, thống nhất conventions, chia kiến thức module, giảm WIP | Ít chờ một người, thời gian tích hợp tốt hơn |
| **4. Phản hồi sản phẩm** | Giao lát cắt nhỏ, cùng người dùng kiểm chứng, đo outcome và chất lượng | Có dữ liệu quyết định bước tiếp theo, không chỉ nhiều ticket Done |

Đây là **ví dụ để lên kế hoạch học**, không phải chuẩn XP bốn tuần bắt buộc. Mỗi vòng có thể kéo dài ngắn hơn hoặc dài hơn tùy sản phẩm, kỹ năng và ràng buộc.

### 13.3. Viết giả thuyết thay vì chỉ viết quy định

~~~text
Vấn đề:
  Lỗi hồi quy trong module lưu tiến độ xuất hiện sau các lần refactor.

Giả thuyết:
  Nếu nhóm viết test hành vi cho các quy tắc quan trọng,
  pair khi sửa phần khó và tích hợp thay đổi nhỏ thường xuyên,
  lỗi hồi quy phát hiện muộn sẽ giảm.

Thử nghiệm:
  Trong nhóm PBI liên quan tới lưu tiến độ, áp dụng
  Red-Green-Refactor với test phù hợp và CI theo chính sách.

Tín hiệu chính:
  Lỗi hồi quy liên quan, thời gian từ commit tới phản hồi,
  thời gian xử lý và số PBI đạt DoD.

Tín hiệu bảo vệ:
  Thời gian test, tình trạng test flaky, chất lượng sau phát hành,
  tải công việc và phản hồi của nhóm.

Điểm xem lại:
  Sau một số vòng làm việc đủ để có dữ liệu có ý nghĩa.

Quyết định:
  Giữ, điều chỉnh hoặc dừng cách làm dựa trên bằng chứng.
~~~

Mẫu này ngăn biến TDD hoặc pairing thành chỉ tiêu “phải đạt 100% số giờ” mà không quan tâm chất lượng thực.

### 13.4. Khi một thực hành làm tăng chi phí

Ví dụ TDD khiến thời gian phát triển ban đầu tăng, hoặc pairing làm hai người không thể giải quyết hai ticket riêng cùng lúc. Điều đó **không tự chứng minh thực hành thất bại**: cần so với số lỗi, thời gian sửa lại, khả năng hiểu code và khả năng hoàn thành Increment.

Ngược lại, không được viện “lợi ích dài hạn” để bỏ qua dữ liệu bất lợi. Nếu test quá giòn, pairing thiếu mục tiêu hoặc CI quá chậm, cần cải thiện cách làm và đánh giá lại.

## 14. Phép đo nào giúp biết các thực hành đang hỗ trợ nhau?

| Loại tín hiệu | Ví dụ | Câu hỏi cần đặt |
|---|---|---|
| **Phản hồi kỹ thuật** | Thời gian CI, tỷ lệ build đỏ và thời gian khôi phục | Khi sai, nhóm biết sớm và sửa được không? |
| **Chất lượng** | Lỗi hồi quy, lỗi nghiêm trọng sau phát hành | Có giảm sự cố lọt tới người dùng không? |
| **Khả năng thay đổi** | Thời gian sửa một quy tắc, phần mã phụ thuộc một người | Refactor và chia kiến thức có hiệu quả không? |
| **Dòng công việc** | Cycle time, throughput, work item age, WIP | Hạng mục có hoàn tất sớm hơn và ít bị chặn hơn không? |
| **Chất lượng test** | Test flaky, thời gian chạy, mức phù hợp với hành vi | Bộ kiểm thử có đáng tin và dễ bảo trì không? |
| **Giá trị sản phẩm** | Tỷ lệ người dùng hoàn thành tác vụ, phản hồi thực | Phần mềm giao sớm có tạo outcome tốt hơn không? |
| **Nhịp làm bền vững** | Làm thêm giờ kéo dài, quá tải review, cảm nhận nhóm | Cải tiến có duy trì được hay gây kiệt sức? |

### 14.1. Đừng tối ưu một chỉ số đơn lẻ

- **Coverage 100%** không chứng minh code không có lỗi hoặc test đã kiểm tra điều quan trọng.
- **CI xanh** không chứng minh người dùng cần tính năng.
- **Velocity cao** có thể do cách chấm điểm thay đổi, không phải năng lực hay giá trị tăng.
- **Throughput tăng** có thể do chia PBI nhỏ tùy tiện hoặc đánh dấu Done sớm.
- **Số giờ pairing cao** không chứng minh tri thức thực sự được chia sẻ.
- **Tần suất phát hành cao** không tự bảo đảm an toàn và hữu ích.

Nên hỏi **cặp tín hiệu**: số lần giao tăng **và** lỗi có giảm/giữ trong mức chấp nhận không? Test chạy nhanh **và** phát hiện hồi quy quan trọng không? Refactor nhiều **và** chi phí thay đổi có cải thiện không?

### 14.2. Cần phân biệt quan sát với nguyên nhân

Giả sử sau khi áp dụng TDD, pairing và CI trong hai Sprint, lỗi hồi quy giảm. Có thể các thực hành góp phần, nhưng cũng có thể phạm vi nhỏ hơn, nhân sự khác, lượng người dùng thấp hoặc chu kỳ đo ngắn.

Không khẳng định nhân quả chỉ từ một đồ thị trước–sau. Hãy:

1. Ghi thời điểm thay đổi, phạm vi PBI và cách đo.
2. Xem mẫu đủ đại diện, phân loại lỗi theo mức tác động.
3. Theo dõi thêm vài vòng và kết hợp phản hồi định tính.
4. Khi cần bằng chứng mạnh hơn, dùng cách so sánh phù hợp với bối cảnh và đạo đức thử nghiệm.

## 15. Những hiểu nhầm thường gặp về hệ thực hành XP

| Hiểu nhầm | Vì sao không đúng | Cách điều chỉnh |
|---|---|---|
| “XP chỉ là TDD.” | Bỏ qua cộng tác, thiết kế, tích hợp và phản hồi khách hàng | Xem TDD là một phần của hệ phản hồi lớn hơn |
| “Có unit test thì refactor luôn an toàn.” | Test có thể sai, thiếu integration và rủi ro bảo mật | Kiểm tra hành vi, ranh giới và chất lượng theo mức rủi ro |
| “Refactoring chỉ làm code đẹp, không tạo giá trị.” | Code khó đổi có thể khiến giao giá trị chậm, lỗi lặp | Liên hệ refactor với khả năng thay đổi và giảm rủi ro |
| “Simple design là không cần kiến trúc.” | Dễ bỏ quên an toàn, dữ liệu và ràng buộc dài hạn đã biết | Thiết kế tối giản **đủ đúng**, cải tiến có test hỗ trợ |
| “Pair programming là một người code, người kia ngồi xem.” | Không tạo trao đổi hai chiều và chia kiến thức | Làm rõ mục tiêu, luân phiên vai, cùng quyết định |
| “Collective ownership nghĩa là ai cũng sửa gì cũng được.” | Có thể vi phạm bảo mật, review và quyền truy cập | Dùng quyền phù hợp, test, CI, standards và trách nhiệm chung |
| “CI là chạy test mỗi tối.” | Tích hợp muộn vẫn tạo xung đột lớn | Tích hợp thay đổi nhỏ thường xuyên và xử lý failure sớm |
| “CI xanh nghĩa là đã phát hành cho khách hàng.” | Nhầm tích hợp với release/deployment | Phân biệt Increment, phát hành và outcome |
| “Small release là đưa mọi thay đổi ngay vào production.” | Có sản phẩm cần rollout và phê duyệt đặc biệt | Giao nhỏ theo quy trình phát hành an toàn |
| “Acceptance test đủ rồi, không cần feedback thật.” | Thông số đúng nhưng giả thuyết nhu cầu có thể sai | Quan sát người dùng và Product Goal |
| “Khách hàng luôn phải ngồi cạnh đội.” | Không phù hợp mọi mô hình phân tán | Bảo đảm đường phản hồi đủ nhanh, tin cậy và đúng thẩm quyền |
| “Sustainable pace là làm ít đi.” | Đánh đồng nhịp bền vững với thiếu trách nhiệm | Giảm làm lại, bảo vệ chất lượng và năng lực lâu dài |
| “Càng nhiều practices áp dụng càng Agile.” | Nghi thức tăng mà không cải thiện feedback | Chọn thực hành theo rủi ro, đo kết quả và điều chỉnh |
| “Đã dùng Scrum thì không thể dùng XP.” | Hai cách nhấn mạnh những phạm vi bổ trợ | Scrum định khung mục tiêu/kiểm tra, XP bổ sung kỹ thuật |
| “XP thay thế kiểm soát bảo mật và pháp lý.” | Có thể vi phạm ràng buộc thực tế | Đưa chuẩn bắt buộc vào DoD và quy trình phù hợp |

## 16. Checklist đánh giá các mối liên kết giữa thực hành

### Về giá trị và yêu cầu

- Nhóm có biết **Product Goal** và vấn đề người dùng đang giải quyết không?
- Có người cung cấp phản hồi nghiệp vụ đủ sớm, đủ rõ không?
- Story được chia thành **lát cắt có giá trị và có thể kiểm chứng** chưa?
- Acceptance criteria có bao gồm những tình huống lỗi/rủi ro quan trọng không?

### Về thiết kế và chất lượng code

- TDD hoặc cách kiểm thử tương đương có giúp phát hiện sai lệch ngay khi tạo code không?
- Bộ test chủ yếu bảo vệ **hành vi cần giữ**, hay đang bám chi tiết triển khai khiến refactor khó?
- Nhóm có refactor thường xuyên để giữ simple design không?
- Những ràng buộc bảo mật, dữ liệu và vận hành có được xem xét đúng lúc không?

### Về cộng tác kỹ thuật

- Pairing/review có thực sự tạo phản hồi và chia sẻ kiến thức không?
- Thành viên có thể chỉnh sửa module cần thiết mà không phải chờ một “chủ sở hữu” duy nhất không?
- Coding standards có rõ và được hỗ trợ bằng công cụ phù hợp không?
- Collective ownership có tuân thủ quyền truy cập và review cần thiết không?

### Về tích hợp và giao giá trị

- Các thay đổi có đủ nhỏ để tích hợp và chẩn đoán thường xuyên không?
- CI có phản hồi nhanh, đáng tin và được xử lý khi đỏ không?
- Increment chỉ được gọi Done khi đáp ứng Definition of Done không?
- Nhóm có giao những phần nhỏ để người dùng hoặc stakeholder kiểm chứng sớm không?
- Có phân biệt **test xanh**, **release thành công** và **outcome người dùng** không?

### Về nhịp làm việc và cải tiến

- WIP và blocker có được quan sát để ưu tiên hoàn tất công việc không?
- Nhóm có duy trì review, test và refactor trong điều kiện công việc bình thường không?
- Các phép đo có bảo vệ chất lượng và sức khỏe nhóm, không chỉ đếm output không?
- Khi một thực hành kém hiệu quả, có giả thuyết điều chỉnh và điểm xem lại không?

Checklist phục vụ **đặt câu hỏi để cải tiến**, không phải một hệ thống chấm điểm XP bắt buộc.

## 17. Bài tập vận dụng

### Bài tập 1 — Vẽ quan hệ hỗ trợ

Chọn bốn thực hành: **TDD, refactoring, CI, pair programming**.

**Yêu cầu:** vẽ một sơ đồ có ít nhất năm mũi tên “A hỗ trợ B vì...”. Thêm một tình huống cho thấy khi một mắt xích bị thiếu, lợi ích của thực hành còn lại giảm.

**Gợi ý:** TDD tạo lưới an toàn khi refactor; refactor giúp thay đổi nhỏ; CI kiểm tra tích hợp; pairing vừa cải thiện test vừa lan kiến thức.

### Bài tập 2 — Khi CI xanh nhưng người dùng không hài lòng

Nhóm có 95% unit test coverage, CI chạy nhanh, nhưng người học vẫn báo mất tiến độ khi mạng yếu.

**Yêu cầu:**

1. Nêu ba lý do vì sao CI xanh không chứng minh luồng lưu đúng.
2. Đề xuất acceptance criteria cho trường hợp lưu thất bại và trạng thái chưa được xác nhận.
3. Chọn các integration/end-to-end tests cần thiết bên cạnh unit tests.
4. Nêu một tín hiệu outcome và hai tín hiệu chất lượng sau phát hành.

**Gợi ý:** có thể unit tests chỉ kiểm tra đường đi thành công hoặc mock không phản ánh hợp đồng API thực. Cần kiểm tra cả UI–API–lưu dữ liệu và hành vi người dùng.

### Bài tập 3 — Refactoring và test quá giòn

Một nhóm muốn tách phương thức dài thành hai phần rõ hơn. Bộ test hiện tại assert thứ tự gọi 12 phương thức nội bộ, nên chỉ đổi cấu trúc nhỏ đã làm vỡ hàng chục test dù output bên ngoài không đổi.

**Yêu cầu:** chỉ ra vấn đề thiết kế test, đề xuất cách chuyển một số test sang kiểm tra hành vi, và giải thích khi nào vẫn cần kiểm tra tương tác nội bộ hoặc hợp đồng.

**Gợi ý:** ưu tiên hành vi quan sát được; mock có ích khi tương tác với dependency là một phần hợp đồng cần bảo vệ, nhưng không nên phụ thuộc mọi bước triển khai.

### Bài tập 4 — Pairing để mở rộng ownership

Một module xác thực chỉ một Developer có thể sửa. Những người khác không dám chỉnh vì thiếu kiến thức, dù pipeline CI hiện khá tốt.

**Yêu cầu:** đề xuất kế hoạch pairing luân phiên trong vài PBI, quy tắc review và cách đánh giá liệu ownership đã được chia sẻ chưa. Nêu thêm các giới hạn bảo mật không được bỏ qua.

**Gợi ý:** có thể xem số người xử lý được lỗi tương tự, thời gian chờ chuyên gia, mức độ tin tưởng test và số lần phải làm lại; không dùng tổng giờ pairing làm kết quả duy nhất.

### Bài tập 5 — Chia story để hỗ trợ small releases

Một epic ghi: **“Đồng bộ tiến độ giữa mọi thiết bị, hỗ trợ offline hoàn toàn, lịch sử chỉnh sửa và giải quyết xung đột.”**

**Yêu cầu:** chia thành ít nhất ba lát cắt tăng dần có giá trị. Với mỗi lát cắt, ghi acceptance criteria chính, rủi ro, kiểm thử và loại phản hồi cần thu thập.

**Gợi ý:** có thể bắt đầu từ lưu và đọc lại một thiết bị có kết nối; sau đó xử lý đổi thiết bị theo quy tắc rõ; rồi mới cân nhắc offline hoặc xung đột phức tạp dựa trên nhu cầu. Mỗi lát cắt phải đủ chất lượng, không đơn thuần hoàn thành một lớp kỹ thuật.

### Bài tập 6 — Tìm vòng đi xuống do áp lực thời hạn

Một đội thường xuyên làm thêm giờ trong hai tuần cuối mỗi bản phát hành. Để kịp, họ bỏ refactoring, chỉ chạy test vào cuối tuần và tích hợp nhánh lớn trước demo.

**Yêu cầu:** vẽ vòng nguyên nhân–hệ quả dẫn tới làm lại và lỗi, rồi đề xuất ba thay đổi **có liên kết hỗ trợ nhau** để đưa đội về nhịp bền vững.

**Gợi ý:** giảm phạm vi và WIP; tích hợp thay đổi nhỏ; giữ kiểm thử và refactor đều; làm rõ lại kỳ vọng phát hành, không dùng làm thêm giờ như nguồn năng lực mặc định.

### Bài tập 7 — Thiết kế thử nghiệm XP có dữ liệu

Nhóm có nhiều lỗi hồi quy khi sửa chức năng giỏ hàng. Trong bốn tuần tới, nhóm muốn thử **TDD + pairing + CI theo lát cắt nhỏ**.

Hãy điền:

~~~text
Vấn đề, Product Goal và bằng chứng nền:
Ba thực hành sẽ áp dụng cùng nhau:
Vì sao thực hành A hỗ trợ B và C:
Phạm vi PBI và loại rủi ro:
Cách kiểm tra hành vi trước khi code:
Cách tích hợp thay đổi nhỏ:
Chính sách khi CI thất bại:
Chỉ số chất lượng cần đo:
Chỉ số flow và feedback cần đo:
Tín hiệu bảo vệ về tốc độ test, tải công việc và sức khỏe nhóm:
Điểm xem lại và điều kiện giữ/điều chỉnh:
~~~

**Gợi ý:** đo lỗi hồi quy, thời gian phát hiện, cycle time, work item age và outcome. Không chỉ đo test coverage và số giờ pairing.

### Bài tập 8 — Chọn cách kết hợp XP với Scrum và Kanban

Một Scrum Team có Sprint Goal “Người dùng có thể hoàn tất thanh toán an toàn”. Giữa Sprint, Kanban board báo nhiều PBI chờ review, một lỗi tạo giao dịch trùng chưa được xử lý và Product Owner đề xuất thêm giao diện khuyến mãi.

**Yêu cầu:**

1. Nêu Sprint Goal và Definition of Done giúp bảo vệ điều gì.
2. Giải thích cách WIP limit và nhìn luồng từ phải sang trái có thể hỗ trợ hoàn tất PBI.
3. Chọn ba thực hành XP để xử lý lỗi giao dịch trùng và giải thích mối liên hệ.
4. Đề xuất cách thương lượng phạm vi với Product Owner mà không hạ chất lượng.
5. Nêu điều cần kiểm tra ở Sprint Review ngoài số ticket Done.

**Gợi ý:** lỗi giao dịch trùng có thể ảnh hưởng nghiêm trọng tới người dùng; cần các kịch bản chấp nhận, test cho hành vi lặp, review/CI và sự minh bạch về rủi ro.

## 18. Tổng kết

XP tạo sức mạnh khi các thực hành **bổ trợ nhau trong một hệ thống phản hồi liên tục**:

1. **TDD cung cấp phản hồi nhỏ; refactoring giữ thiết kế dễ thay đổi; simple design giúp những thay đổi tiếp theo vẫn nhỏ và rõ.**
2. **Pair programming tạo phản hồi và lan kiến thức; coding standards giảm ma sát; collective code ownership giúp nhóm sửa đúng nơi cần; CI bảo vệ việc cùng thay đổi.**
3. **Thay đổi nhỏ giúp CI dễ chẩn đoán; CI đáng tin giúp tích hợp thường xuyên; small releases đưa Increment tới người dùng để nhận phản hồi thật.**
4. **Customer collaboration, user stories và acceptance tests** giữ kỹ thuật hướng tới hành vi có giá trị, không chỉ làm pipeline xanh.
5. **Sustainable pace và kiểm soát WIP** giúp nhóm còn khả năng duy trì kiểm thử, review và cải tiến, thay vì tạo vòng lặp quá tải–lỗi–làm lại.
6. **Kết hợp với Scrum và Kanban khi phù hợp:** Scrum giữ định hướng mục tiêu và DoD, Kanban quản lý dòng công việc, XP cung cấp những thực hành kỹ thuật hỗ trợ Increment đáng tin.
7. **Thực hành tốt cần được kiểm chứng bằng kết quả:** xem chất lượng, khả năng thay đổi, flow và outcome người dùng; không dùng số lượng practices, coverage hay tốc độ phát hành làm mục tiêu tự thân.

> **Câu hỏi ghi nhớ:** “Nếu bỏ đi một thực hành XP trong nhóm, **những thực hành nào sẽ mất sự hỗ trợ, phản hồi nào sẽ đến muộn hơn và rủi ro nào sẽ tăng** — và chúng ta có bằng chứng nào để quyết định?”

### Tài liệu tham khảo

- [Agile Alliance — Extreme Programming (XP)](https://agilealliance.org/glossary/xp/) — giới thiệu phương pháp XP, các thực hành và tư duy cộng tác, phản hồi, chất lượng kỹ thuật.
- [Extreme Programming — extremeprogramming.org](http://www.extremeprogramming.org/) — tổng quan các thực hành XP cổ điển và cách chúng bổ trợ nhau; đối chiếu với bối cảnh áp dụng hiện đại.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản thứ hai — các giá trị, nguyên tắc và thực hành XP cùng khả năng thích ứng với thay đổi.
- [Martin Fowler — Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html) — tư duy tích hợp thường xuyên, phản hồi nhanh và xử lý lỗi tích hợp.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Product Goal, Sprint Goal, Increment, Definition of Done và kiểm tra–thích ứng.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, throughput, work item age và cycle time.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — giao phần mềm giá trị sớm, chú trọng chất lượng kỹ thuật, phản hồi và cải tiến liên tục.
