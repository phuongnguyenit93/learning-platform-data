# Nhận diện và giảm phụ thuộc giữa các nhóm

## 1. Khi nhiều nhóm cùng tạo giá trị, phụ thuộc trở thành một phần của luồng công việc

Trong một dự án nhỏ, vài Developers có thể cùng thay đổi giao diện, API, dữ liệu và kiểm thử để tạo ra một Increment có thể sử dụng. Khi sản phẩm mở rộng, tổ chức có thể có nhóm phụ trách trải nghiệm web, đăng ký khóa học, định danh, thông báo, nền tảng triển khai và các dịch vụ dùng chung.

Giả sử mục tiêu là **học viên tự đăng ký một khóa học miễn phí còn chỗ và nhận xác nhận chính xác**. Một luồng tưởng chừng đơn giản có thể cần:

- Nhóm web hiển thị trạng thái khóa và xác nhận đăng ký.
- Nhóm đăng ký bảo vệ quy tắc không trùng, không vượt sức chứa.
- Nhóm định danh bảo đảm học viên được xác thực và chỉ truy cập dữ liệu của mình.
- Nhóm nền tảng cung cấp môi trường tích hợp, pipeline và khả năng quan sát.
- Nhóm thông báo gửi xác nhận khi phù hợp với phạm vi sản phẩm.

Nếu nhóm web không thể kiểm tra luồng trước khi có API; nhóm đăng ký chờ hợp đồng định danh; tất cả chờ một môi trường tích hợp duy nhất, **mỗi nhóm có thể đang bận và hoàn thành task riêng nhưng người học vẫn chưa nhận được giá trị**.

**Phụ thuộc giữa các nhóm (cross-team dependency)** là tình huống mà khả năng tiến tới một kết quả của nhóm này bị ràng buộc bởi **công việc, quyết định, tài nguyên, thông tin, giao diện hoặc thời điểm** thuộc trách nhiệm hoặc ảnh hưởng của nhóm khác.

Trong module **AGILE_DEVELOPMENT**, mục tiêu không phải loại bỏ mọi quan hệ giữa con người. Hợp tác là thiết yếu. Mục tiêu là **giảm thời gian chờ và chi phí phối hợp không cần thiết**, làm rõ các phụ thuộc còn lại và tạo điều kiện giao phần mềm tăng dần, nhận phản hồi sớm, duy trì chất lượng.

> **Nguyên tắc:** Tối ưu mức sử dụng của từng nhóm không đồng nghĩa tối ưu tốc độ và chất lượng giao giá trị **xuyên qua nhiều nhóm**.

### 1.1. Một luồng giá trị đi qua nhiều ranh giới

~~~mermaid
flowchart LR
    A["Nhu cầu học viên"] --> B["Làm rõ hành vi đăng ký"]
    B --> C["Web + API + dữ liệu + quyền"]
    C --> D["Tích hợp và kiểm chứng"]
    D --> E["Increment dùng được"]
    E --> F["Phát hành và quan sát"]
    F --> G["Phản hồi để cải tiến"]
~~~

Các hộp là **hoạt động tạo giá trị**, không bắt buộc tương ứng từng phòng ban. Khi một luồng đi qua quá nhiều cổng bàn giao, việc chờ phê duyệt, đổi ngữ cảnh, làm lại và tìm người phụ trách có thể lớn hơn thời gian thực sự tạo mã.

### 1.2. Kết quả học tập

Sau bài này, người học có thể:

1. Nhận diện **loại, hướng, thời điểm và hậu quả** của phụ thuộc giữa các nhóm.
2. Mô tả phụ thuộc bằng sơ đồ, bảng hoặc một bản ghi có **owner, điều kiện hoàn tất, hạn cần biết và mức rủi ro**.
3. Phân biệt cách **loại bỏ/giảm phụ thuộc ở cấu trúc công việc** với cách **điều phối phụ thuộc không thể tránh**.
4. Áp dụng giao diện hợp đồng, lát cắt dọc, kiểm thử tích hợp, chính sách luồng và đồng bộ mục tiêu để giảm chờ.
5. Đo tác động lên **cycle time, work item age, WIP, thời gian blocked, chất lượng và outcome**.
6. Nhận biết phản mẫu như họp đồng bộ nhiều nhưng không có quyết định, “Done cục bộ” nhưng chưa có Increment, hoặc chuyển hàng đợi sang nhóm khác.

## 2. Phân biệt phụ thuộc, hợp tác, ràng buộc và điểm nghẽn

### 2.1. Không phải mọi tương tác đều là phụ thuộc gây cản trở

Một Developer hỏi chuyên gia bảo mật để hiểu chính sách truy cập là **hợp tác**. Nó trở thành **phụ thuộc có thể gây chờ** nếu công việc không thể hoàn tất khi chưa có kết quả đánh giá, người có quyền ra quyết định không sẵn sàng và không có cơ chế làm rõ sớm.

| Khái niệm | Câu hỏi phân biệt | Ví dụ |
| --- | --- | --- |
| **Hợp tác** | Nhiều bên cùng đóng góp để tạo giá trị? | Backend và frontend cùng thảo luận response schema. |
| **Phụ thuộc** | Kết quả của một bên có phải chờ đầu ra/điều kiện từ bên khác? | Web chưa thể test luồng thật vì API contract chưa được thống nhất. |
| **Ràng buộc** | Giới hạn bắt buộc nào chi phối giải pháp? | Yêu cầu bảo mật cần xác minh quyền trước khi phát hành. |
| **Điểm nghẽn** | Nơi nào năng lực hoặc chính sách khiến luồng tích tụ hàng đợi? | Một reviewer duy nhất phê duyệt mọi thay đổi DB. |
| **Blocker** | Điều gì đang thực tế ngăn item tiếp tục ở thời điểm này? | Môi trường tích hợp không truy cập được. |
| **Rủi ro phụ thuộc** | Điều gì có thể ngăn item ở tương lai dù chưa bị chặn? | Đối tác dự kiến đổi API vào tuần tới. |

Phụ thuộc có thể **hợp lý hoặc bắt buộc**: ví dụ hệ thống thu học phí phải dùng dịch vụ kiểm soát giao dịch theo quy định. Điều cần giảm là **chờ đợi, bất định và thay đổi phải làm lại**, không phải bỏ kiểm soát an toàn để được gọi là “tự chủ”.

### 2.2. Phụ thuộc có thể tồn tại ở nhiều cấp độ

- **Một task:** web cần trường thông tin từ API.
- **Một Product Backlog Item (PBI):** tính năng đăng ký cần quyền định danh.
- **Một Increment:** các phần từ nhiều nhóm phải tích hợp và đạt Definition of Done.
- **Một mục tiêu sản phẩm:** nhiều năng lực tổ chức cần phối hợp để người dùng thực sự tự đăng ký.
- **Vận hành lâu dài:** nhóm xử lý sự cố cần thông tin và quyền từ nhóm quản lý nền tảng.

Khi ghi phụ thuộc, phải nói rõ **đối tượng bị ảnh hưởng**. “Phụ thuộc nhóm nền tảng” quá mơ hồ; “PBI đăng ký không thể hoàn tất kiểm thử đồng thời vì thiếu database test được phân quyền” cụ thể hơn.

### 2.3. Phụ thuộc không tự biến mất khi tạo ticket

Một thẻ “chờ team X” không bảo đảm đầu ra sẽ tới đúng thời điểm. Quản lý phụ thuộc cần tối thiểu:

- Bên **cần** một đầu ra/điều kiện.
- Bên **có thể cung cấp hoặc ra quyết định**.
- Đầu ra/điều kiện đủ rõ để **kiểm chứng**.
- Thời điểm cần theo mục tiêu, dự báo có mức bất định.
- Rủi ro nếu chậm và phương án thay thế nếu có.
- Cơ chế **liên lạc, escalation và xác nhận hoàn tất**.

## 3. Phân loại phụ thuộc để chọn đối sách đúng

### 3.1. Các nhóm phụ thuộc thường gặp

| Loại phụ thuộc | Ví dụ trong nền tảng học trực tuyến | Hướng xử lý thường phù hợp |
| --- | --- | --- |
| **Nghiệp vụ / quyết định** | Chưa thống nhất có giữ chỗ khi học viên bắt đầu thao tác không. | Đưa Product Owner/người có thẩm quyền vào refinement sớm, dùng ví dụ cụ thể. |
| **Thứ tự công việc (precedence)** | Mã dùng một hợp đồng mới chỉ có thể bật sau khi backend tương thích. | Chia thay đổi theo thứ tự an toàn, giữ tương thích chuyển tiếp. |
| **Kỹ thuật / API** | Frontend và backend chưa nhất trí về mã trạng thái. | Consumer/provider contract, schema review, contract tests. |
| **Dữ liệu / migration** | Hai nhóm cùng thay bảng enrollment hoặc event schema. | Owner rõ, migration từng bước, kiểm chứng các phiên bản cùng tồn tại. |
| **Hạ tầng / môi trường** | Nhiều nhóm tranh một môi trường staging hoặc tài khoản cloud. | Tự phục vụ có giới hạn, môi trường cách ly, chính sách cấp tài nguyên. |
| **Chuyên môn / quyền duyệt** | Chỉ một người đủ quyền review thay đổi bảo mật nhạy cảm. | Mở rộng năng lực và người dự phòng khi hợp lệ; review sớm theo rủi ro. |
| **Lịch triển khai / phát hành** | Web và API buộc phải cập nhật đồng thời. | Giảm coupling bằng hợp đồng tương thích, flag/rollout có kế hoạch. |
| **Nhà cung cấp / đối tác** | Dịch vụ xác thực ngoài thay đổi phiên bản token. | Đầu mối hợp đồng, môi trường thử, fallback, thời gian dự phòng. |
| **Vận hành / hỗ trợ** | Chưa có runbook, monitoring hoặc người trực để rollout. | Cùng thiết kế readiness từ đầu, không giao hồ sơ vào ngày cuối. |
| **Tổ chức / ưu tiên** | Một nền tảng dùng chung nhận yêu cầu từ sáu nhóm. | Minh bạch công suất, chính sách ưu tiên chung và đầu tư vào khả năng tự phục vụ. |

**Chọn nhầm đối sách** dễ làm tăng chi phí. Ví dụ, nếu nút thắt là một môi trường tích hợp không ổn định, tăng số buổi lập kế hoạch liên nhóm có thể không giúp nhiều. Nếu phụ thuộc do hợp đồng API không rõ, tăng số máy CI cũng không giải quyết nguyên nhân.

### 3.2. Phụ thuộc bên trong nhóm và giữa nhóm

| Khía cạnh | Phụ thuộc trong cùng nhóm liên chức năng | Phụ thuộc giữa nhiều nhóm |
| --- | --- | --- |
| **Trao đổi** | Có thể phối hợp trực tiếp thường xuyên. | Cần tìm đúng người, bối cảnh và kênh liên lạc. |
| **Ưu tiên** | Thường có mục tiêu gần chung. | Có thể có Product Goal hoặc trách nhiệm dịch vụ khác nhau. |
| **Quyền quyết** | Thường dễ làm rõ trong nhóm. | Có thể chịu chính sách, hợp đồng hoặc quyền liên tổ chức. |
| **Phản hồi** | Thường ngắn hơn khi cùng codebase/test. | Dễ chậm vì hàng đợi review và lịch phát hành khác nhau. |
| **Cách giảm** | Pairing, chia lát cắt, quản lý WIP. | Hợp đồng rõ, chuẩn giao tiếp, giảm coupling, self-service, liên kết mục tiêu. |

Không phải nhóm đa chức năng nào cũng tránh được phụ thuộc. Nhưng thiết kế nhóm sao cho **phần lớn những thay đổi giá trị thông thường có thể hoàn tất trong nhóm** thường giảm nhu cầu chuyển giao không cần thiết.

### 3.3. Phụ thuộc “cứng”, “mềm” và cách kiểm chứng

Có thể phân nhóm phục vụ thảo luận (không phải phân loại chuẩn chính thức):

- **Cứng:** không thể tiếp tục hoặc bàn giao hợp lệ khi chưa đạt điều kiện khác, như schema phải hỗ trợ dữ liệu trước khi bật hành vi ghi mới.
- **Mềm:** có thể tiến hành một phần với giả định/cơ chế tạm an toàn, như frontend dùng contract mock đã thống nhất trong lúc backend triển khai.
- **Tự tạo bởi quy trình:** ví dụ tất cả PR nhỏ phải chờ một cuộc họp cố định hằng tuần dù quy tắc có thể được kiểm chứng tự động.

**Mock giúp bắt đầu sớm**, nhưng không biến hợp đồng giả thành tích hợp thật. Phải có contract/integration tests trên các thành phần thật trước khi coi Increment đáp ứng chuẩn chất lượng cần thiết.

## 4. Nhận diện phụ thuộc từ một lát cắt giá trị, không chỉ sơ đồ tổ chức

### 4.1. Bắt đầu bằng kết quả người dùng

Nếu xuất phát từ danh sách đội “frontend”, “backend”, “DBA”, “platform”, người lập kế hoạch dễ chia backlog theo phòng ban. Thay vào đó, bắt đầu với:

> **Hành trình:** học viên đã đăng nhập thấy khóa còn chỗ, gửi đăng ký một lần và nhận trạng thái chính xác, không tạo bản ghi trùng hoặc vượt sức chứa.

Sau đó hỏi:

1. Để người dùng nhận kết quả, **hành vi nào** phải có?
2. Những thành phần nào cùng tham gia **một đường thực thi**?
3. Ai sở hữu quyết định/hợp đồng/dữ liệu quan trọng?
4. Điều gì nhóm đang làm **không thể tự kiểm chứng**?
5. Nếu phần bên ngoài chậm, nhóm còn tạo lát cắt giá trị nhỏ hơn nào an toàn không?
6. Có những phụ thuộc đã tồn tại nhưng **chưa được ai ghi lại** không?

### 4.2. Dependency mapping theo giá trị

~~~mermaid
flowchart TD
    Goal["Outcome: học viên tự đăng ký đáng tin cậy"]
    Goal --> Web["Luồng Web"]
    Goal --> Enroll["Đăng ký và kiểm soát sức chứa"]
    Goal --> Auth["Xác thực và phân quyền"]
    Goal --> Quality["Tích hợp và kiểm thử"]
    Goal --> Ops["Triển khai, quan sát, hỗ trợ"]
    Web -. "Hợp đồng trạng thái" .-> Enroll
    Enroll -. "Danh tính hợp lệ" .-> Auth
    Quality -. "Môi trường, dữ liệu test" .-> Ops
    Enroll -. "Đúng dữ liệu cuối" .-> Quality
    Web -. "Kiểm chứng hành trình" .-> Quality
~~~

Các cạnh nét đứt biểu thị **nhu cầu phối hợp hoặc điều kiện cần được làm rõ**, không có nghĩa mọi cạnh đều là blocker ở thời điểm hiện tại.

### 4.3. Vẽ cả phụ thuộc ngược và vòng tròn

Ví dụ:

- Web chờ API response của Enrollment.
- Enrollment chờ Web thống nhất khi nào cần trả lỗi hết chỗ.

Nếu hai nhóm đều ghi “chờ bên kia”, ta có **vòng phụ thuộc**. Giải pháp không phải chỉ đẩy hạn sớm hơn. Họ cần trao đổi đồng thời, thống nhất **hợp đồng tối thiểu, ví dụ dữ liệu và người quyết định** rồi có thể phát triển song song với kiểm thử hợp đồng.

Một vòng phụ thuộc thường là tín hiệu:

- Một quyết định chung chưa có owner.
- Các nhóm chia theo lớp kỹ thuật thay vì theo lát cắt giá trị.
- Giao diện thay đổi liên tục hoặc khó kiểm thử.
- Hệ thống đang có coupling mạnh.

### 4.4. Gắn phụ thuộc với điểm bàn giao và hàng đợi

Không chỉ vẽ **ai chờ ai**. Hãy quan sát cả:

- Khi nào yêu cầu được chuyển?
- Nó nằm trong hàng đợi bao lâu?
- Mỗi lần chuyển phải làm rõ lại những thông tin nào?
- Có bao nhiêu vòng review/trả lại vì sai hợp đồng?
- Khi một bên thay đổi, các bên khác mất bao lâu để được biết?
- Có cơ chế xác nhận kết quả **trên bản tích hợp** hay không?

Nhiều tương tác có thể lành mạnh; **hàng đợi dài và thiếu tiêu chuẩn bàn giao** mới là rủi ro cần cải tiến.

## 5. Biểu diễn phụ thuộc bằng đồ thị và ma trận

### 5.1. Đồ thị có hướng

Một sơ đồ phụ thuộc có thể dùng:

- **Nút (node):** hạng mục công việc, capability, dịch vụ hoặc quyết định.
- **Cạnh có hướng:** điều kiện mà một nút cần từ nút khác.
- **Nhãn cạnh:** hợp đồng, ngày cần, trạng thái, owner hoặc nguy cơ.

Quy ước cần ghi rõ. Trong bài này, ta định nghĩa:

> **A → B** nghĩa là **A cần đầu ra hoặc điều kiện từ B** để hoàn tất theo tiêu chuẩn đã chọn.

Với quy ước ấy, nếu **Web → Enrollment API**, phần Web đang **phụ thuộc vào** API Enrollment, không phải Web có trách nhiệm cung cấp API cho Enrollment.

### 5.2. Ma trận phụ thuộc (Dependency Structure Matrix — DSM)

Giả sử có bốn năng lực:

- **W:** giao diện Web.
- **E:** dịch vụ Enrollment.
- **I:** định danh và phân quyền.
- **P:** nền tảng CI/triển khai.

Theo quy ước **hàng là bên cần**, **cột là bên cung cấp/điều kiện**:

| Bên cần ↓ / Bên cung cấp → | W | E | I | P |
| --- | :---: | :---: | :---: | :---: |
| **W** | — | ✓ | ✓ | ✓ |
| **E** |  | — | ✓ | ✓ |
| **I** |  |  | — | ✓ |
| **P** |  |  |  | — |

Ma trận minh họa cho thấy:

- Web cần hợp đồng Enrollment và xác thực, cũng như môi trường chạy phù hợp.
- Enrollment cần xác thực và môi trường kiểm chứng.
- Identity có thể cần khả năng của nền tảng.
- Platform trong ví dụ không phụ thuộc vào ba bên còn lại **cho lát cắt đang xét**, không có nghĩa platform không có khách hàng hay phụ thuộc khác.

Mỗi dấu ✓ **không có trọng số ngang nhau**. Một yêu cầu quyền kiểm tra bắt buộc có thể rủi ro cao, một yêu cầu cấu hình nhỏ có thể xử lý nhanh. Có thể bổ sung **mức ảnh hưởng, hạn cần, trạng thái, thời gian chờ** ngoài ma trận, nhưng tránh biến bảng thành nơi cập nhật thủ công nặng hơn giá trị nó mang lại.

### 5.3. Cẩn trọng với “đường găng” trong phát triển thích ứng

Với các công việc có thời lượng tương đối rõ và thứ tự bắt buộc, **critical path** có thể giúp thấy chuỗi công việc quyết định mốc hoàn thành. Tuy nhiên:

- Thời lượng công việc tri thức thường bất định.
- Có nhiều vòng phản hồi/rework, không phải một đồ thị bất biến.
- Thay đổi yêu cầu có thể làm một đường khác quan trọng hơn.
- Chờ review, môi trường, quyền hoặc test không tự thể hiện trong “ước lượng coding”.

Hãy dùng sơ đồ để **nhận diện rủi ro phối hợp và lựa chọn giảm phụ thuộc**, không dùng nó để khẳng định một ngày giao chính xác khi chưa có bằng chứng.

### 5.4. Nhận diện vòng phụ thuộc

Một chu trình như **A → B → C → A** có thể khiến các nhóm cùng chờ hoặc liên tục làm lại. Cách tháo:

1. Tìm **quyết định chung** hoặc hợp đồng nào chưa rõ.
2. Mời đúng bên có quyền quyết định và đủ bối cảnh tới một trao đổi ngắn.
3. Chọn **lát cắt nhỏ**, interface hoặc test để kiểm chứng giả định chung.
4. Xác định thứ tự triển khai **tương thích**, không cần “tất cả xong rồi mới merge”.
5. Ghi lại các quyết định làm thay đổi nghĩa vụ hoặc dữ liệu của nhóm khác.

Một dependency graph hiện tại không nên bị coi là “kiến trúc lý tưởng”. Đôi khi việc giảm số cạnh bằng thay đổi ranh giới sở hữu hoặc API mới tạo hiệu quả lớn hơn việc tối ưu lịch họp quanh mạng phụ thuộc cũ.

## 6. Ghi dependency register ngắn gọn, có thể hành động

### 6.1. Bản ghi tối thiểu

| Trường | Câu hỏi |
| --- | --- |
| **Mã / tiêu đề** | Đang nói tới phụ thuộc nào, liên kết với công việc nào? |
| **Consumer / provider** | Ai cần gì từ ai? |
| **Đầu ra/điều kiện** | Một artifact, API, quyết định hay môi trường nào là đủ? |
| **Mốc cần theo mục tiêu** | Khi nào cần để không chặn lát cắt? Có dự báo và mức bất định? |
| **Owner trao đổi** | Ai chủ động cập nhật hoặc xác minh? |
| **Mức rủi ro/tác động** | Nếu chậm hoặc sai, ai bị ảnh hưởng, điều gì không thể Done? |
| **Trạng thái và bằng chứng** | Chưa thống nhất, đang làm, blocked, có thể dùng, đã kiểm chứng? |
| **Phương án giảm/né** | Có thể đổi lát cắt, mock contract, fallback hoặc tự phục vụ không? |
| **Escalation** | Khi nào cần người có thẩm quyền hoặc phối hợp cao hơn? |

### 6.2. Ví dụ dependency register cho nền tảng học trực tuyến

| ID | Bên cần → bên cung cấp | Cần gì? | Rủi ro | Owner và bước tiếp |
| --- | --- | --- | --- | --- |
| **D-01** | Web → Enrollment | Hợp đồng API trạng thái đăng ký và lỗi hết chỗ. | UI làm theo giả định sai, phải viết lại. | Hai đầu mối cùng chốt ví dụ request/response, thêm contract test. |
| **D-02** | Enrollment → Identity | Quy tắc lấy học viên đã xác thực, phân quyền tra trạng thái. | Lộ dữ liệu hoặc chặn test E2E. | Chủ sở hữu Identity làm rõ claim/permission; Enrollment kiểm thử trái quyền. |
| **D-03** | Enrollment → Platform | DB/test environment cho kiểm thử hai người tranh chỗ cuối. | Không xác minh được nhất quán dữ liệu. | Platform cấp môi trường theo quy trình; team Enrollment đề xuất tự phục vụ. |
| **D-04** | Web/Enrollment → Platform | CI tích hợp, quy tắc triển khai và quan sát. | PR xanh nhưng bản chung lỗi; rollout khó khôi phục. | Cùng định nghĩa check bắt buộc và runbook. |
| **D-05** | Enrollment → Notification | Hợp đồng phát sự kiện đăng ký đã xác nhận nếu notification thuộc phạm vi. | Gửi thông báo sai hoặc lặp. | Làm rõ idempotency/owner event; có thể tách khỏi lát cắt MVP nếu giá trị cho phép. |

**Không tự gán tất cả D-01 đến D-05 là PBI độc lập.** Có thể một PBI cần nhiều điều kiện, hoặc một hạng mục nền tảng giảm phụ thuộc cho nhiều PBI. Quan trọng là rõ **ai cần điều gì để tạo giá trị**, không phải tạo thật nhiều thẻ.

### 6.3. Mô tả “đã hoàn tất phụ thuộc” bằng điều kiện kiểm chứng

Một trạng thái như **“API team nói đã xong”** chưa đủ. Ví dụ D-01 chỉ được xem là đã đáp ứng khi:

- Hợp đồng request/response và mã lỗi được thống nhất.
- Có phiên bản provider tương thích hoặc môi trường kiểm chứng phù hợp.
- Consumer kiểm tra được những kịch bản cần thiết.
- Các giới hạn và thay đổi tương lai được công bố.

Phần phụ thuộc được đáp ứng **không tự làm PBI sử dụng nó trở thành Done**. PBI còn phải đạt các điều kiện nghiệp vụ và Definition of Done tương ứng.

### 6.4. Ví dụ thẻ phụ thuộc ngắn

~~~text
DEPENDENCY: D-03 — Môi trường kiểm thử đăng ký đồng thời
Consumer: Nhóm Enrollment, PBI đăng ký khóa miễn phí
Provider: Nhóm Platform
Đầu ra: môi trường DB test cách ly, có khả năng tạo hai request đồng thời
Vì sao cần: xác minh không ghi quá sức chứa
Trạng thái: đang chờ quyền cấp tài nguyên
Mốc cần kiểm chứng: trước quyết định Done của PBI
Rủi ro: không thể xác nhận tính nhất quán dữ liệu theo DoD
Đầu mối: kỹ sư Enrollment và người phụ trách Platform
Bước kế tiếp: thống nhất mẫu cấu hình và cách tự phục vụ an toàn
Escalation: khi mốc tích hợp có nguy cơ bị chặn
Điều kiện kết thúc: test cạnh tranh chạy đạt trên bản tích hợp thích hợp
~~~

Đây là **dữ liệu giả để học tập**, không phải một yêu cầu đã tồn tại trong tổ chức. Với hệ thống thật, bản ghi cần dẫn tới ticket, owner và dữ liệu đã được xác minh.

## 7. Quản lý phụ thuộc theo giá trị, hậu quả và thời điểm

### 7.1. Không phải phụ thuộc nào cũng cần họp khẩn cấp

Có thể đánh giá:

1. **Tác động lên mục tiêu:** phụ thuộc có chặn Sprint Goal/Product Goal hay chỉ thay đổi một tiện ích tùy chọn?
2. **Mức độ bắt buộc:** không có đầu ra thì không đạt DoD, hay có lát cắt an toàn thay thế?
3. **Độ bất định:** provider đã cam kết và kiểm chứng được gì, hay chưa có người phụ trách?
4. **Thời gian phản hồi:** có đủ sớm để phát hiện sai hợp đồng và sửa?
5. **Số nhóm bị ảnh hưởng:** một thay đổi có gây lỗi dây chuyền không?
6. **Hậu quả nếu sai:** dữ liệu, bảo mật, vận hành, người dùng có bị tác động?

Đánh giá này giúp tập trung **năng lực phối hợp hữu hạn** vào phụ thuộc có thể chặn giá trị hoặc gây hậu quả cao.

### 7.2. Ma trận lựa chọn hành động

| Tình huống | Cách phản ứng |
| --- | --- |
| Đầu ra nhỏ, hợp đồng rõ, provider sẵn sàng | Thống nhất cách kiểm chứng, tích hợp sớm, không cần họp phối hợp dài. |
| Phụ thuộc lớn nhưng có thể chia lát cắt | Thu hẹp scope và tách thay đổi tương thích để giao sớm. |
| Phụ thuộc do hàng đợi review hoặc quyền duyệt | Công khai tuổi chờ, điều chỉnh năng lực hoặc người dự phòng hợp lệ. |
| Phụ thuộc API có nguy cơ đổi hợp đồng | Chốt contract, dùng contract tests, thông báo thay đổi và versioning khi cần. |
| Phụ thuộc dữ liệu hoặc an toàn nghiêm trọng | Đưa chuyên gia có thẩm quyền tham gia sớm; không bỏ kiểm soát để chạy nhanh. |
| Đối tác chưa có lịch đáng tin | Đánh dấu rủi ro, tìm fallback và kiểm tra khả năng chia phạm vi. |
| Phụ thuộc xảy ra lặp lại trên nhiều luồng | Xem lại ranh giới nhóm, kiến trúc hoặc mô hình dịch vụ nền tảng. |

### 7.3. Tránh “ngày cam kết chính xác” khi còn bất định

Với công việc khám phá hoặc tích hợp chưa từng làm, câu **“team B sẽ giao 16:00 thứ Sáu”** có thể chỉ tạo ảo giác chắc chắn. Tốt hơn:

- Làm rõ **đầu ra nhỏ nhất có thể kiểm chứng**.
- Nêu mốc **cần biết** hoặc điểm ra quyết định, không phải chỉ mốc giao.
- Ghi những giả định ảnh hưởng dự báo.
- Đặt cơ chế kiểm tra sớm, cập nhật ngay khi rủi ro thay đổi.
- Chuẩn bị lát cắt thay thế hoặc kế hoạch điều chỉnh Sprint Backlog nếu phù hợp.

**Minh bạch bất định** không phải né trách nhiệm. Provider vẫn có trách nhiệm thông tin rõ; consumer có trách nhiệm không giữ các giả định im lặng tới phút cuối.

### 7.4. Escalation phải giải quyết quyết định, không chỉ tăng số người nhận tin

Một phụ thuộc bị chặn có thể cần:

- **Chuyên môn:** người hiểu API/schema, dữ liệu hoặc an toàn đưa ra giải pháp.
- **Thẩm quyền:** người có quyền cấp tài nguyên, điều chỉnh ưu tiên hoặc chấp nhận phương án hợp lệ.
- **Điều phối:** người giữ bức tranh chung giúp hai nhóm cùng lên kế hoạch thay vì gửi yêu cầu qua nhiều lớp.

Khi escalation, nói rõ **quyết định cần đưa ra, tác động, thời điểm cần biết và các lựa chọn**. Chỉ thêm người quản lý vào một cuộc họp mà không xác định quyết định cần thiết thường không giảm hàng đợi.

## 8. Giảm phụ thuộc bằng cách thiết kế lại lát cắt công việc

### 8.1. Lát cắt ngang chức năng và lát cắt dọc giá trị

Một kế hoạch theo lớp kỹ thuật:

~~~text
Nhóm A: hoàn thành giao diện đăng ký.
Nhóm B: hoàn thành toàn bộ API đăng ký.
Nhóm C: thay mọi cấu trúc dữ liệu liên quan.
Nhóm D: viết tất cả test tích hợp vào cuối đợt.
~~~

Kế hoạch này có thể tạo nhiều “task Done cục bộ” nhưng phụ thuộc lớn khi ghép.

Một cách tiếp cận theo **lát cắt dọc (vertical slice)**:

1. Học viên đã đăng nhập xem được trạng thái **còn chỗ** từ dữ liệu thật trong phạm vi nhỏ.
2. Học viên gửi yêu cầu đăng ký một khóa miễn phí và có phản hồi tương ứng.
3. Bảo vệ tính đúng đắn khi retry/tranh chỗ cuối, kiểm thử tích hợp theo rủi ro trước khi gọi chức năng Done.
4. Thêm cách tự xác minh trạng thái sau mất phản hồi mạng.

**Lưu ý:** không chia theo cách làm cho một Increment được tuyên bố Done trước khi đạt quy tắc an toàn bắt buộc. Một lát cắt không có kiểm soát sức chứa dù hệ thống cho người dùng đăng ký thật **không phải một Increment hoàn tất an toàn** chỉ vì “sẽ sửa trong lát cắt 3”. Các bước kỹ thuật có thể được merge an toàn dưới cơ chế chưa mở sử dụng; khả năng người dùng chỉ được coi Done khi đáp ứng DoD.

### 8.2. Giảm số lần bàn giao bằng hợp tác sớm

Một **lát cắt dọc** có thể cần nhiều năng lực, nhưng nếu người có năng lực cần thiết cùng làm trên một mục tiêu nhỏ, số vòng **yêu cầu → chờ → hiểu sai → trả lại** thường có cơ hội giảm.

Nhóm có thể thử:

- **Three Amigos** hoặc refinement đa góc nhìn cho PBI quan trọng.
- **Pairing/swarming** giữa chuyên môn có phụ thuộc cao trong thời gian ngắn.
- **Bàn giao hợp đồng rõ**, ví dụ Gherkin và mẫu dữ liệu.
- **Chia sẻ test** để xác nhận thay vì tranh luận “bên nào lỗi”.
- **Làm việc trên một phiên bản tích hợp** sớm thay vì chờ tất cả nhánh hoàn chỉnh.

Không cần ghép mọi người vào một cuộc họp cố định lớn. Mời **đúng người, đúng quyết định, đúng thời điểm** thường hiệu quả hơn.

### 8.3. Khi nào cần thay đổi ranh giới sở hữu?

Nếu một nhóm phải chờ ba nhóm khác cho **hầu hết** hạng mục giá trị thường ngày, đó có thể là dấu hiệu tổ chức đang chia quá sâu theo lớp kỹ thuật hoặc quyền sở hữu dịch vụ.

Có thể cân nhắc:

- Nhóm **liên chức năng, hướng luồng giá trị** có khả năng tự tạo phần lớn Increment.
- Chuyển quyền sở hữu một thành phần kèm tài liệu, test và năng lực rõ ràng.
- Tạo **platform self-service** cho môi trường, CI và hạ tầng lặp lại.
- Dùng một nhóm **enabling** hỗ trợ nâng năng lực rồi giảm phụ thuộc lâu dài.
- Xem lại biên giới giữa các dịch vụ có coupling thay đổi quá lớn.

Việc đổi cấu trúc nhóm là một quyết định có chi phí và hệ quả dài hạn. Không nên làm chỉ vì một PBI bị chặn một lần; cần xem **tần suất, tác động, kỹ năng, kiến trúc, công suất và mục tiêu sản phẩm**.

### 8.4. Không nhầm task kỹ thuật với Increment có giá trị

Một hệ thống có thể cần PR thêm trường database, PR bổ sung contract, PR viết UI và PR triển khai test. Các thay đổi nhỏ đó hữu ích để **tích hợp kỹ thuật thường xuyên**, nhưng không nên gọi từng PR là Increment hoàn tất nếu chưa có phần sản phẩm dùng được và đáp ứng DoD.

Ngược lại, một **Increment** có thể được hình thành từ nhiều thay đổi nhỏ và phối hợp giữa nhiều nhóm. Cần một tiêu chuẩn chất lượng chung cho những phần thuộc cùng sản phẩm, không chỉ các bộ test độc lập của từng đội.

## 9. API contract và kiểm thử hợp đồng để giảm phụ thuộc chờ đợi

### 9.1. Thống nhất hành vi trước khi hoàn tất triển khai

Nhóm Web và Enrollment cần một hợp đồng cho việc đăng ký. Thay vì chờ backend triển khai xong toàn bộ, các bên có thể thống nhất:

- Endpoint và quyền gọi.
- Request/response, trường bắt buộc và ý nghĩa.
- Cách biểu diễn **đã đăng ký, hết chỗ, yêu cầu lặp, lỗi tạm thời**.
- Quy tắc retry/idempotency và phản hồi khi không biết trạng thái.
- Versioning/deprecation nếu API đang có consumer khác.
- Test hợp đồng của cả bên cung cấp và bên sử dụng.

Ví dụ response **minh họa**, không phải quy ước bắt buộc:

~~~json
{
  "enrollmentId": "ENR-EXAMPLE-001",
  "courseId": "COURSE-EXAMPLE-01",
  "state": "CONFIRMED",
  "message": "Đã ghi nhận đăng ký"
}
~~~

API còn cần trả mã trạng thái HTTP phù hợp và bảo vệ quyền truy cập theo thiết kế cụ thể; **không được dùng trạng thái trong JSON làm thay thế xác thực/phân quyền**.

### 9.2. Consumer-driven contract testing

Một phương pháp có thể cân nhắc là **consumer-driven contract testing**: các consumer mô tả những kỳ vọng họ thật sự cần; provider kiểm chứng những kỳ vọng ấy với phiên bản phù hợp.

Lợi ích tiềm năng:

1. Phát hiện sớm thay đổi response/schema khiến Web hỏng.
2. Giảm thời gian chờ đến E2E hoàn chỉnh mới biết lệch hợp đồng.
3. Làm rõ trách nhiệm khi một provider có nhiều consumer.
4. Cho phép tích hợp các thay đổi nhỏ mà vẫn kiểm tra tính tương thích.

Nhưng contract tests **không thay thế integration tests** trên DB, giao dịch đồng thời hoặc kiểm thử hành trình người dùng. Hai nhóm có thể cùng chấp nhận một hợp đồng sai nghiệp vụ; khi ấy tất cả contract tests xanh nhưng hệ thống vẫn không đáp ứng Product Goal.

### 9.3. Mock và stub: giúp làm song song nhưng không thay được kiểm chứng thật

| Công cụ | Lợi ích | Giới hạn |
| --- | --- | --- |
| **Mock/stub có hợp đồng** | Web hoặc consumer phát triển sớm, giảm chờ code provider. | Có thể khác hành vi provider thật nếu hợp đồng không được kiểm tra. |
| **Contract test** | Phát hiện tương thích giao diện. | Không chứng minh dữ liệu/transaction hoặc hiệu năng toàn hệ thống. |
| **Integration test** | Kiểm tra các thành phần cùng chạy thật trong môi trường phù hợp. | Có thể nặng/chậm nếu không tổ chức tốt. |
| **End-to-end test** | Kiểm tra hành trình quan trọng của người dùng. | Không bao phủ mọi điều kiện và có thể khó tái hiện. |
| **Observability khi rollout** | Phát hiện hành vi thực và sự cố chưa lộ. | Không thay thế kiểm soát an toàn trước release. |

Để giảm phụ thuộc, nhóm nên **đưa phản hồi tới sớm** chứ không chỉ chuyển nghĩa vụ kiểm tra sang cuối quy trình.

### 9.4. Hợp đồng thay đổi theo hướng tương thích

Khi một API có nhiều consumer:

1. **Mở rộng** hợp đồng theo cách không phá consumer hiện hành nếu có thể.
2. Chuyển consumer sang cách mới, kiểm thử tương thích.
3. Theo dõi những consumer còn dùng hợp đồng cũ.
4. **Loại bỏ** phần cũ khi đã xác minh đủ điều kiện và đúng chính sách deprecation.

Đây là tư duy **expand–migrate–contract** có thể áp dụng cả schema dữ liệu lẫn giao tiếp dịch vụ. Một thay đổi nhỏ ở provider không nên buộc mọi nhóm cùng deploy trong một phút nếu có thể thiết kế tương thích an toàn.

## 10. Giảm coupling triển khai và quản lý thay đổi dữ liệu giữa các nhóm

### 10.1. Coupling là gì khi có nhiều nhóm?

**Coupling** thể hiện mức các thành phần hoặc nhóm phải biết về thay đổi bên kia, sửa đồng thời hoặc cùng được triển khai để một hành vi hoạt động. Một thay đổi giao diện nhỏ cần phối hợp năm phiên bản API và ba schema DB thường là tín hiệu **coupling cao**.

Không phải coupling nào cũng tránh được. Nhưng nếu mọi lần cải tiến đều cần “đồng bộ toàn hệ thống”, độ trễ và rủi ro release tăng.

### 10.2. Giảm phụ thuộc triển khai bằng hợp đồng tương thích

Ví dụ dịch vụ Enrollment muốn đổi trường trạng thái. Nếu xóa trường cũ ngay khi thêm trường mới, các client chưa nâng cấp có thể hỏng. Thay vào đó:

1. Bổ sung trường mới theo cách được consumer hiện hành hỗ trợ.
2. Kiểm chứng cả phiên bản API cũ và mới theo chính sách.
3. Chuyển từng consumer, đo sử dụng hợp đồng.
4. Thông báo thời điểm chấm dứt trường cũ theo quy trình deprecation.
5. Chỉ xóa khi có bằng chứng những consumer cần thiết đã chuyển.

**Tương thích ngược không phải đảm bảo tự động**: một client có thể không chấp nhận enum hoặc field lạ. Cần kiểm thử với hợp đồng và cách parser thực tế hoạt động.

### 10.3. Thay đổi DB: expand–migrate–contract

Một thay đổi schema lớn thường nên được thực hiện theo những bước **không bắt mọi nhóm deploy cùng lúc**:

~~~mermaid
flowchart LR
    A["Schema cũ đang hoạt động"] --> B["Expand: bổ sung cấu trúc tương thích"]
    B --> C["Migrate: chuyển logic/dữ liệu có kiểm soát"]
    C --> D["Xác minh mọi consumer liên quan"]
    D --> E["Contract: gỡ phần cũ theo chính sách"]
~~~

Lưu ý với dữ liệu thật:

- Không tự thay cột, bảng hoặc ràng buộc production khi thiếu thẩm quyền.
- Có kế hoạch quan sát, rollback/forward-fix và bảo vệ dữ liệu.
- Xét thời gian hai phiên bản cùng tồn tại trong rolling deployment.
- Kiểm tra rằng cả mã cũ và mới có thể xử lý dữ liệu hợp lệ trong giai đoạn chuyển tiếp.
- Thử migrations trên môi trường phù hợp với rủi ro khóa bảng, hiệu năng và tính nhất quán.

**Rollback code không tự hoàn tác dữ liệu đã ghi hoặc email đã gửi.** Cách giảm phụ thuộc phải giữ khả năng khôi phục thực, không chỉ thay đổi thứ tự deployment trên giấy.

### 10.4. Feature flags và branch by abstraction

| Kỹ thuật | Dùng để giảm phụ thuộc nào? | Rủi ro phải quản lý |
| --- | --- | --- |
| **Feature flag** | Merge/deploy mã an toàn trước khi mở hành vi, giảm nhu cầu đồng bộ ngày release. | Không thay authn/authz; nhiều cờ cũ làm khó kiểm thử; cần owner và kế hoạch gỡ. |
| **Branch by abstraction** | Thay một thành phần lớn qua nhiều tích hợp nhỏ thay vì giữ nhánh dài. | Abstraction chuyển tiếp và hai cách triển khai tăng phức tạp; cần test tương đương. |
| **Versioned contract** | Consumer và provider có thể nâng cấp lệch nhịp. | Chính sách version/deprecation, kiểm thử tương thích và support. |
| **Idempotent operation** | Giảm rủi ro gửi lại message/request khi các hệ thống giao tiếp bất đồng bộ. | Cần định nghĩa business key, tính đúng đắn dữ liệu và giới hạn retry. |
| **Event-driven communication** | Giảm coupling đồng bộ thời gian thực trong một số trường hợp. | Tăng độ phức tạp nhất quán cuối, xử lý lặp, ordering, observability. |

Không chọn microservices, event bus hoặc feature flags **chỉ vì muốn giảm số lượng dependency trong sơ đồ**. Một kiến trúc phân tán không được thiết kế kỹ có thể làm **nhiều phụ thuộc runtime và vận hành hơn**.

## 11. Phụ thuộc về hạ tầng, chuyên môn và nền tảng dùng chung

### 11.1. Nhóm nền tảng có thể là điểm hỗ trợ hoặc nút thắt

Một nhóm nền tảng có thể cung cấp:

- Mẫu CI/CD đã kiểm chứng và khả năng tự cấu hình trong giới hạn.
- Môi trường test cách ly, dữ liệu giả và công cụ dựng hệ thống.
- Logging, metrics, tracing và cảnh báo dùng chung.
- Quy tắc danh tính và quyền truy cập tích hợp.
- Công cụ bảo mật, secret management, dependency scanning.
- Mẫu triển khai/rollback có quyền và phê duyệt cần thiết.

Nếu mọi thay đổi nhỏ phải gửi ticket cho platform và xếp hàng chờ, **một nhóm giúp nhiều đội lại trở thành điểm nghẽn liên tục**. Giảm phụ thuộc thường cần chuyển các yêu cầu lặp lại, ít rủi ro thành **khả năng tự phục vụ (self-service) được kiểm soát**.

### 11.2. Self-service không đồng nghĩa “ai cũng có quyền làm mọi thứ”

Một khả năng tự phục vụ tốt có:

1. Giao diện hoặc quy trình yêu cầu rõ, ít bước.
2. Mẫu cấu hình an toàn, có kiểm tra tự động.
3. Phân quyền và ngân sách/công suất phù hợp.
4. Có quan sát và khả năng truy vết thay đổi.
5. Hướng dẫn xử lý lỗi thông thường.
6. Đường hỗ trợ khi có ngoại lệ, rủi ro cao hoặc hành vi ngoài dự kiến.

Ví dụ, Developers có thể tạo **môi trường DB thử nghiệm cách ly** theo template, nhưng không được tự tạo database production với dữ liệu học viên thật mà không có quyền và kiểm soát.

### 11.3. Giảm phụ thuộc vào chuyên gia duy nhất

Khi chỉ một người hiểu schema, hệ thống build hoặc quyền truy cập, toàn tổ chức dễ bị chặn khi người ấy bận. Các biện pháp khả dĩ:

- Pairing theo thay đổi thật, không chỉ buổi chuyển giao lý thuyết.
- Viết hướng dẫn quyết định quan trọng và runbook ngắn.
- Tạo kiểm tra tự động giúp tri thức thành bằng chứng có thể lặp lại.
- Có người review dự phòng **đủ năng lực và thẩm quyền**, không ký duyệt hình thức.
- Giới hạn WIP chuyên môn ở nơi đang quá tải.
- Dành năng lực nâng kỹ năng thay vì yêu cầu chuyên gia làm mọi thứ.

Nhưng với các bước bắt buộc phải do người có chứng chỉ/quyền cụ thể thực hiện, **không tự mở rộng quyền** chỉ để giảm hàng đợi. Khi đó cần cải thiện năng lực, dự báo và đường phối hợp hợp lệ.

### 11.4. Nhìn công suất của dịch vụ dùng chung

Một platform team nhận yêu cầu của nhiều sản phẩm có thể không thể ưu tiên theo **Sprint Goal của riêng một đội**. Nếu mỗi nhóm xem nhu cầu của mình là khẩn cấp, việc đổi ưu tiên liên tục làm tổng thời gian chờ tăng.

Giải pháp có thể gồm:

| Tình huống | Cách cải thiện |
| --- | --- |
| Nhiều ticket nhỏ lặp lại | Tạo API/template self-service có guardrails. |
| Nhiều yêu cầu cùng mốc cần | Công khai công suất, rủi ro và chính sách ưu tiên. |
| Nhiều cấu hình giống nhau phải phê duyệt thủ công | Tự động hóa kiểm tra điều kiện được phép. |
| Mọi dự án đều phụ thuộc một chuyên gia | Phát triển năng lực, tài liệu và reviewer dự phòng hợp lệ. |
| Không biết ticket thuộc nhóm nào | Danh mục dịch vụ, owner, đường escalation rõ. |
| Một nhóm thay đổi có tác động toàn sản phẩm | Cơ chế công bố hợp đồng và review ảnh hưởng liên nhóm. |

Không biến platform team thành “bộ phận phải giao mọi yêu cầu ngay lập tức”. **Tối ưu dòng giá trị của toàn hệ thống** cần cân bằng năng lực, mức rủi ro và các mục tiêu sản phẩm.

## 12. Thiết kế ranh giới nhóm để giảm phụ thuộc lặp lại

### 12.1. Các kiểu chia nhóm và hệ quả

| Mô hình tổ chức công việc | Lợi ích thường thấy | Nguy cơ phụ thuộc |
| --- | --- | --- |
| **Theo lớp kỹ thuật**: Web, API, DB, QA | Tập trung chuyên môn, dễ tiêu chuẩn hóa trong phạm vi hẹp. | Một tính năng giá trị phải đi qua nhiều hàng đợi. |
| **Theo capability/luồng giá trị** | Nhiều năng lực cùng chịu trách nhiệm một hành trình người dùng. | Cần phối hợp nền tảng hoặc miền dữ liệu chung, có thể trùng lặp công nghệ. |
| **Theo thành phần dùng chung** | Có owner ổn định cho thành phần phức tạp. | Owner trở thành người duyệt mọi thay đổi, queue tăng. |
| **Platform product / self-service** | Giảm việc lặp và giúp nhóm sản phẩm tự phục vụ. | Nếu platform không coi nhóm phát triển là khách hàng, sẽ tạo API/tool khó dùng. |
| **Nhóm hỗ trợ nâng năng lực (enabling)** | Giúp nhóm sản phẩm học kỹ thuật khó, giảm phụ thuộc dài hạn. | Nếu chỉ nhận ticket làm hộ, nhóm sản phẩm tiếp tục phụ thuộc. |

Một tổ chức có thể kết hợp nhiều mô hình. Không có sơ đồ tổ chức hoàn hảo cho mọi sản phẩm và giai đoạn.

### 12.2. Team Topologies như công cụ tư duy

**Team Topologies** mô tả một số kiểu nhóm thường được dùng để thảo luận thiết kế tổ chức: **stream-aligned, platform, enabling, complicated-subsystem**; đồng thời nhấn mạnh những kiểu tương tác như **collaboration, X-as-a-Service và facilitating**.

Đây là **một mô hình tham khảo**, không phải cấu phần chính thức của Scrum hay quy định cần có đúng bốn loại nhóm trong mọi tổ chức.

Ví dụ áp dụng:

- Một **stream-aligned team** chịu trách nhiệm hành trình học viên tự đăng ký.
- Một **platform team** cung cấp CI, môi trường và giám sát dưới dạng sản phẩm nội bộ.
- Một **enabling team** hỗ trợ nhóm luồng giá trị phát triển kỹ năng kiểm thử giao dịch đồng thời.
- Một **complicated-subsystem team** có thể sở hữu thành phần tối ưu lịch/xếp lớp rất chuyên sâu nếu chi phí nhận thức thực sự đòi hỏi.

Điểm cần kiểm tra không phải tên nhóm đúng từ vựng, mà là **nhóm nào có thể giao giá trị tương đối độc lập, tương tác có chủ đích và không làm quá tải năng lực nhận thức**.

### 12.3. Ranh giới phần mềm và ranh giới giao tiếp ảnh hưởng nhau

**Conway's Law** thường được dùng để giải thích rằng thiết kế hệ thống và cấu trúc giao tiếp của tổ chức có xu hướng ảnh hưởng lẫn nhau. Nếu mọi thay đổi đều cần năm nhóm ký duyệt, kiến trúc có thể dần phản ánh những ranh giới ấy; nếu một dịch vụ dùng chung không có contract và self-service, nhiều nhóm phải gắn chặt vào lịch làm việc của đội sở hữu.

Tuy nhiên, **không dùng quy luật này như tiên đoán tuyệt đối**: kiến trúc tốt còn phụ thuộc giới hạn miền nghiệp vụ, an ninh, dữ liệu, chi phí và chuyên môn. Thay đổi cấu trúc nhóm khi chưa hiểu hệ thống có thể làm tăng rủi ro.

### 12.4. Khi nào nên giữ một phụ thuộc?

Một phụ thuộc có thể **đáng giữ** nếu:

- Bảo vệ một chính sách an toàn, dữ liệu hoặc tuân thủ bắt buộc.
- Cho phép tái sử dụng capability ổn định với hợp đồng rõ và chi phí tương tác thấp.
- Giữ một chuyên môn thực sự phức tạp tại nơi đủ khả năng vận hành và bảo trì.
- Tránh nhân bản một subsystem đắt hoặc nguy hiểm ở nhiều nơi.

Khi ấy mục tiêu là **làm phụ thuộc dễ dự đoán, có thể kiểm chứng và ít chờ**, thay vì cố xóa nó khỏi sơ đồ.

## 13. Đồng bộ nhiều Scrum Team mà không làm sai Scrum

### 13.1. Một sản phẩm, nhiều Scrum Team: cần điểm tựa chung

Theo **Scrum Guide 2020**, khi nhiều Scrum Team cùng làm trên **một sản phẩm**, họ cần:

- Cùng hướng về **một Product Goal**.
- Chia sẻ **một Product Backlog**.
- Có **một Product Owner** cho sản phẩm, không phải hội đồng nhiều Product Owner có quyền ngang nhau.
- Có cùng **Definition of Done** khi cùng làm một sản phẩm.

Điều này khác với trường hợp nhiều nhóm làm **những sản phẩm độc lập** có Product Goal và Product Backlog riêng nhưng có API/phụ thuộc chung. Không nên gộp tất cả chỉ vì chúng cùng ở một hệ sinh thái.

### 13.2. Một DoD chung không đồng nghĩa mỗi team chạy một bộ test riêng rồi cộng lại

Ví dụ:

- Nhóm Web đạt test giao diện.
- Nhóm Enrollment đạt unit tests.
- Nhóm Identity đạt test xác thực.

Nếu bản tích hợp vẫn cho người khác đọc đăng ký trái quyền, **chưa có Increment đáp ứng DoD** cho hành vi đó. Chất lượng phải được kiểm chứng ở những ranh giới liên quan, không cộng ba lần “xong cục bộ” thành một “xong sản phẩm”.

### 13.3. Phụ thuộc trong Sprint Planning

Khi Sprint Planning, Developers cân nhắc:

1. Sprint Goal của nhóm cần những điều kiện nào?
2. Có phụ thuộc làm mục tiêu không khả thi theo dự báo không?
3. Có thể chia lát cắt hoặc làm rõ hợp đồng trước khi chọn việc không?
4. Ai sẽ chủ động làm việc với bên cung cấp đầu ra?
5. Những rủi ro tích hợp cần kiểm tra sớm hơn ngày cuối?
6. Nếu bên ngoài thay đổi ưu tiên, nhóm có thể thích ứng Sprint Backlog ra sao?

**Sprint Backlog thuộc Developers**, được cập nhật trong suốt Sprint; không nên biến buổi họp điều phối liên nhóm thành nơi quản lý áp đặt danh sách task bất chấp Sprint Goal.

### 13.4. Daily Scrum không phải cuộc họp báo cáo liên nhóm

Trong Scrum, Daily Scrum là sự kiện 15 phút của **Developers** để kiểm tra tiến độ hướng Sprint Goal và điều chỉnh Sprint Backlog. Nó **không bắt buộc** phải là cuộc họp mọi nhóm báo cáo cho một quản lý trung tâm.

Khi có một phụ thuộc giữa các nhóm:

- Những người liên quan có thể trao đổi trực tiếp sau Daily Scrum.
- Có thể cùng chạy một phiên tích hợp/kiểm thử để chốt vấn đề.
- Có thể dùng một kênh async rõ thông tin và quy ước phản hồi.
- Cần escalation nếu quyền hoặc thứ tự ưu tiên không thể giải quyết ở cấp đang làm.

Đừng chờ tới cuộc họp tổng hợp hằng tuần nếu có thể giải quyết hợp đồng API bằng một cuộc trao đổi kỹ thuật ngắn ngay hôm nay.

### 13.5. Scrum of Scrums, Nexus và mô hình mở rộng

Trong thực hành mở rộng, tổ chức có thể dùng:

- **Scrum of Scrums** như một cách phối hợp giữa đại diện các nhóm về trở ngại/tích hợp.
- **Nexus** như một framework mở rộng được thiết kế nhằm tăng khả năng tạo Increment tích hợp của nhiều Scrum Team cùng sản phẩm.
- Các cuộc refinement/kiểm thử tích hợp hoặc điều phối roadmap chung phù hợp ngữ cảnh.

Những cách này **không phải các sự kiện hoặc vai trò bắt buộc của Scrum Guide áp dụng cho mọi đội**. Một cuộc Scrum of Scrums không tự giải quyết phụ thuộc kỹ thuật nếu không có **owner, quyết định, hợp đồng và kiểm chứng bản tích hợp**.

Nếu cuộc họp chỉ liệt kê “team A đang chờ team B” mỗi lần, nó đang **theo dõi phụ thuộc** nhưng chưa **giảm phụ thuộc**.

## 14. Kanban và flow metrics để nhìn thấy thời gian chờ liên nhóm

### 14.1. Biểu diễn công việc xuyên qua các nhóm

Một luồng tham khảo:

~~~mermaid
flowchart LR
    A["Ready"] --> B["Developing"]
    B --> C["Cross-team review / contract"]
    C --> D["Integrated verification"]
    D --> E["Done theo policy"]
    C -. "Blocked / rework" .-> B
    D -. "Rework" .-> B
~~~

Điểm quan trọng không phải tên cột, mà là **Definition of Workflow (DoW)**: các loại item, mốc bắt đầu/kết thúc, chính sách chuyển trạng thái, cách kiểm soát WIP và xử lý blocked.

Nếu công việc vẫn chưa đạt Finished nhưng bị kéo ra khỏi bảng khi “gửi cho team khác”, bảng có thể đẹp hơn trong khi **thời gian thực của người dùng chưa được rút ngắn**.

### 14.2. Bốn flow metrics nền tảng

| Metric | Cách hiểu | Ứng dụng khi có phụ thuộc |
| --- | --- | --- |
| **WIP** | Số item đã Started nhưng chưa Finished tại một thời điểm. | Thấy công việc đang bị đẩy vào nhiều hàng đợi. |
| **Cycle time** | Thời gian Started → Finished của item hoàn tất. | Đo tốc độ hoàn tất xuyên nhiều bước, không chỉ coding. |
| **Work item age** | Thời gian item đang dở tính từ Started tới hiện tại. | Thấy phụ thuộc đang làm các item cũ ngày càng già. |
| **Throughput** | Số item Finished trong một khoảng thời gian. | Quan sát nhịp hoàn tất của cả hệ thống, tránh chỉ đếm task cục bộ. |

Một PBI chờ review ngoài nhóm vẫn là **WIP** nếu nó đã Started nhưng chưa Finished theo chính sách. Đừng cho item “ngủ” ở một bảng khác để che tuổi chờ.

### 14.3. Đo blocked time, nhưng định nghĩa cho rõ

Ví dụ, một PBI có chu trình:

| Hoạt động | Thời gian minh họa |
| --- | ---: |
| Phát triển và kiểm chứng cục bộ | 2 ngày |
| Chờ hợp đồng API từ nhóm khác | 3 ngày |
| Tích hợp và sửa sai lệch | 1 ngày |
| Chờ môi trường E2E | 2 ngày |
| Kiểm chứng cuối và đạt Done | 1 ngày |
| **Tổng cycle time** | **9 ngày** |

Theo cách chia **không chồng lấn thời gian** trong ví dụ, phần chờ thuần là **5/9 ngày**, tức khoảng **55,6%** chu kỳ. Đây là ví dụ cho thấy giảm hàng đợi có thể hữu ích hơn ép người viết code nhanh hơn.

Nhưng trong thực tế, các hoạt động có thể **chồng lấn** hoặc có chờ xen kẽ với công việc khác. Muốn tính tỷ lệ blocked hợp lệ phải công bố mốc, cách đếm, dữ liệu và tránh cộng trùng giờ.

### 14.4. Service Level Expectation không phải lời hứa cứng

Kanban có thể dùng **Service Level Expectation (SLE)**: kỳ vọng có tính xác suất cho thời gian hoàn tất theo workflow và tập dữ liệu thích hợp. SLE giúp thấy item nào có nguy cơ vượt nhịp thường gặp, từ đó hỏi sớm về phụ thuộc.

SLE không tự là hợp đồng **SLA**, không bảo đảm mọi item hoàn tất đúng một số ngày và không phải lý do bỏ test/DoD. Khi các item có loại, kích cỡ và rủi ro khác nhau, cần phân nhóm hoặc chú thích để dự báo có ý nghĩa.

### 14.5. Little's Law trong ngữ cảnh hàng đợi

Với một hệ thống luồng tương đối ổn định và thỏa các điều kiện áp dụng, **Little's Law** mô tả quan hệ giữa mức WIP trung bình, thông lượng và thời gian trung bình:

\[
\overline{\text{WIP}}\approx
\text{Throughput rate}\times\overline{\text{Cycle time}}.
\]

Ví dụ minh họa: nếu luồng ổn định có trung bình **12 item đang dở** và hoàn tất trung bình **4 item/tuần**, thời gian trong hệ thống trung bình xấp xỉ:

\[
\frac{12}{4}=3\text{ tuần}.
\]

Kết quả này không bảo đảm một PBI bất kỳ sẽ xong sau đúng ba tuần. Nếu hàng đợi thay đổi nhanh, phạm vi Started/Finished không nhất quán hoặc throughput không ổn định, không nên áp công thức như một dự báo chính xác.

## 15. Cơ chế phối hợp thực dụng giữa các nhóm

### 15.1. Thiết kế nhịp phù hợp với tính chất phụ thuộc

| Mức nhịp | Hoạt động minh họa | Mục tiêu |
| --- | --- | --- |
| **Ngay khi phát sinh** | Hai đầu mối cùng giải quyết một contract mismatch qua chat/call/pairing. | Phản hồi nhanh, không chờ cuộc họp định kỳ. |
| **Hằng ngày khi đang tích hợp** | Kiểm tra item blocked hoặc PR/mainline lỗi liên nhóm. | Giữ luồng ổn định và bảo vệ Sprint Goal. |
| **Khi chuẩn bị chọn việc** | Refinement/kiểm tra phụ thuộc, ví dụ chấp nhận chung. | Chia lát cắt và giảm rủi ro trước khi bắt đầu. |
| **Trước các mốc release** | Kiểm tra tương thích, runbook, quyền, rollout và điều kiện dừng. | Bảo đảm phát hành an toàn dù các nhóm deploy lệch nhịp. |
| **Theo chu kỳ cải tiến** | Xem dependency age, blocked time, hàng đợi và lỗi tích hợp. | Chọn phụ thuộc lặp lại để loại bỏ bằng kỹ thuật/tổ chức. |

Không nên đồng nhất **phối hợp tốt với nhiều cuộc họp**. Một hợp đồng API được ghi rõ và test tự động có thể giảm nhiều vòng hỏi–đáp.

### 15.2. Working agreements liên nhóm

Một thỏa thuận làm việc có thể gồm:

- Cách công bố **consumer/provider owner** và kênh liên lạc.
- Mẫu yêu cầu đủ bối cảnh, không thiếu đầu ra hoặc điều kiện kiểm chứng.
- Thời điểm review hợp đồng khi có thay đổi phá tương thích.
- Thời gian phản hồi được kỳ vọng **theo loại yêu cầu và năng lực**, không hứa SLA tùy tiện.
- Chính sách blocked, escalation, thay đổi thứ tự ưu tiên và truyền thông rủi ro.
- Cách đảm bảo CI/mainline, test tích hợp và các phiên bản cùng tồn tại.
- Người có thẩm quyền thay đổi production và quy trình khôi phục.
- Thời điểm đánh giá thỏa thuận và loại bỏ thủ tục gây chờ không cần thiết.

**Working agreement không phải quyền tự bỏ chuẩn bảo mật hoặc phê duyệt bắt buộc.** Nó làm cách phối hợp minh bạch, có thể điều chỉnh dựa trên bằng chứng.

### 15.3. Quyết định cần ghi lại và truyền tới bên bị ảnh hưởng

Khi một quyết định thay đổi hành vi API, dữ liệu hoặc quyền:

1. Ghi **vấn đề và những lựa chọn** có liên quan.
2. Chỉ rõ người có quyền quyết và người phải được tham vấn.
3. Nêu **quyết định, lý do, ảnh hưởng**, phiên bản và chiến lược chuyển tiếp.
4. Thông báo các consumer bị ảnh hưởng và cách kiểm chứng.
5. Cập nhật tài liệu/contract tests khi cần.

Một **Architecture Decision Record (ADR)** ngắn có thể hữu ích cho quyết định kỹ thuật ảnh hưởng nhiều nhóm. Với thay đổi nhỏ và rõ, mô tả trong PR/ticket có thể đủ; không cần tạo ADR cho mọi dòng code.

### 15.4. RACI/DACI chỉ để làm rõ trách nhiệm, không thay công việc nhóm

Các bảng như **RACI** (Responsible, Accountable, Consulted, Informed) hoặc **DACI** (Driver, Approver, Contributors, Informed) có thể hữu ích khi một quyết định liên nhóm cứ bị trì hoãn vì **không ai biết ai có quyền quyết**.

Không nên dùng chúng để tạo tầng duyệt cho mọi thao tác. Cũng cần tránh nhập nhằng giữa **Accountable trong một bảng quyết định** và các **accountabilities chính thức của Scrum**. Bảng điều phối không thể tự thay Product Owner, Developers hay Scrum Master.

### 15.5. Escalation cần đi kèm phương án

Thay vì nhắn “Team B làm chúng tôi trễ”, một thông điệp điều phối có thể là:

> “PBI đăng ký hiện chưa thể kiểm thử trên DB tích hợp vì D-03 chưa đáp ứng. Điều kiện cần là môi trường cách ly chạy test tranh chỗ cuối; nếu không có trước mốc kiểm chứng tiếp theo, PBI không đạt DoD. Chúng tôi đề xuất dùng template môi trường thử đã được Platform phê duyệt; cần xác nhận quyền cấp và đầu mối hỗ trợ.”

Thông điệp này chỉ rõ **ảnh hưởng, điều kiện, phương án, quyền và bước tiếp**, tăng khả năng đưa ra quyết định hơn là thông báo trách móc.

## 16. Tình huống xuyên suốt: bốn nhóm cùng giao chức năng đăng ký khóa học

### 16.1. Bối cảnh và ranh giới sản phẩm

Giả sử một doanh nghiệp phát triển nền tảng học trực tuyến có Product Goal:

> Học viên đủ điều kiện có thể tự đăng ký khóa học miễn phí còn chỗ và biết trạng thái chính xác, không phải nhờ nhân viên hỗ trợ các trường hợp thông thường.

Có bốn nhóm phối hợp:

| Nhóm giả định | Phạm vi chính | Điều họ cần từ bên khác |
| --- | --- | --- |
| **Journey** | Giao diện web và trải nghiệm đăng ký. | Enrollment API, quy tắc xác thực, môi trường tích hợp. |
| **Enrollment** | Quy tắc đăng ký, sức chứa, idempotency và dữ liệu. | Identity contract, DB test, CI/observability. |
| **Identity** | Xác thực, claims, quyền truy cập và các hợp đồng danh tính. | Cấu hình nền tảng và hiểu nhu cầu quyền của consumer. |
| **Platform** | CI, môi trường thử, khả năng triển khai/quan sát theo chính sách. | Yêu cầu năng lực rõ ràng để cung cấp self-service hiệu quả. |

Bốn nhóm trên chỉ là **ví dụ tổ chức**. Nếu tất cả cùng làm **một sản phẩm theo Scrum**, cần duy trì các điều kiện Scrum đã nêu ở mục 13. Nếu Platform cung cấp một sản phẩm nội bộ độc lập hoặc Identity là sản phẩm nền tảng phục vụ nhiều sản phẩm khác, có thể có backlog/PO riêng theo ranh giới sản phẩm thật; cần **quy tắc phối hợp và quyết định ưu tiên giữa các sản phẩm**.

### 16.2. Hành vi nghiệp vụ và chuẩn chất lượng chung

Điều kiện chấp nhận quan trọng:

1. Học viên đăng nhập và đủ quyền.
2. Khóa học miễn phí có chỗ trống tại thời điểm xác nhận.
3. Một học viên không có hai đăng ký hiệu lực cho cùng khóa.
4. Hai người tranh chỗ cuối không thể cùng được xác nhận vượt sức chứa.
5. Người học biết trạng thái đúng sau thành công, hết chỗ, lỗi tạm thời hoặc retry.
6. Người dùng không thể đọc dữ liệu đăng ký riêng của người khác.

Đây không phải toàn bộ đặc tả hệ thống thật. Nhưng bất kỳ lát cắt được tuyên bố **Done** nào cho hành vi đăng ký thực cũng phải giữ những kiểm soát liên quan theo phạm vi/DoD, không trì hoãn phần an toàn tới “nhóm khác sẽ làm Sprint sau”.

### 16.3. Bản đồ phụ thuộc ban đầu

~~~mermaid
flowchart LR
    J["Journey: UI"] -. "D-01: contract" .-> E["Enrollment: API + dữ liệu"]
    E -. "D-02: claims / quyền" .-> I["Identity"]
    E -. "D-03: DB test" .-> P["Platform"]
    J -. "D-04: CI / staging" .-> P
    I -. "D-05: config / secrets" .-> P
~~~

Theo quy ước trong bài, mũi tên từ **bên cần** tới **bên cung cấp điều kiện**. Mỗi cạnh cần được kiểm tra xem có thể giảm, xử lý song song hoặc chuyển thành hợp đồng ổn định không.

### 16.4. Phân biệt ba tình trạng ban đầu

| Phụ thuộc | Quan sát giả định | Đánh giá sơ bộ |
| --- | --- | --- |
| **D-01: API contract** | Journey đã viết UI theo giả định, chưa thống nhất response khi hết chỗ. | Rủi ro làm lại; có thể giải quyết nhanh bằng ví dụ và contract test. |
| **D-02: Identity** | Identity có API ổn định nhưng nhóm Enrollment không biết claim nào được bảo đảm. | Vấn đề tri thức/hợp đồng, chưa chắc cần đổi API. |
| **D-03: DB test** | Platform cấp môi trường theo ticket; môi trường dùng chung đang quá tải. | Nút thắt năng lực và quy trình có khả năng lặp lại. |
| **D-04: CI/staging** | Có pipeline cục bộ nhưng chưa kiểm tra phiên bản phối hợp. | Nguy cơ “xanh riêng lẻ, đỏ khi ghép”. |
| **D-05: secrets/config** | Identity cần chính sách cấp quyền hợp lệ. | Phụ thuộc có thể bắt buộc; nên giảm chờ bằng template an toàn chứ không bỏ duyệt. |

Không nên đưa cả năm cạnh vào danh sách **blocker đang xảy ra** nếu một số chỉ là rủi ro tương lai hoặc nhu cầu làm rõ.

## 17. Lập kế hoạch giảm phụ thuộc trước khi bắt đầu và trong khi làm

### 17.1. Bước 1 — Cùng chốt hành trình giá trị

Product Owner và người hiểu nghiệp vụ xác nhận:

- Lát cắt đầu **chỉ gồm khóa miễn phí**, không thu học phí.
- Không cần email xác nhận trong phạm vi đầu nếu giao diện đã xác minh được trạng thái và người dùng có thể biết kết quả đúng.
- Quy tắc không trùng, không vượt sức chứa và quyền riêng tư là **bắt buộc**.
- Kết quả người dùng quan trọng hơn việc mọi nhóm báo đã hoàn thành số task riêng.

Nếu email xác nhận là một cam kết nghiệp vụ bắt buộc, không được tùy tiện loại bỏ. Cần hỏi người có quyền quyết định về giá trị/phạm vi, đồng thời tuân thủ những nghĩa vụ áp dụng.

### 17.2. Bước 2 — Chốt hợp đồng sớm để giảm chờ

Journey và Enrollment cùng thống nhất ví dụ:

~~~json
{
  "requestId": "REQ-EXAMPLE-01",
  "courseId": "COURSE-EXAMPLE-01",
  "result": "CONFIRMED",
  "enrollmentId": "ENR-EXAMPLE-01"
}
~~~

Các tình huống cần thống nhất:

| Kịch bản | Quy tắc phản hồi cần rõ |
| --- | --- |
| Đăng ký mới thành công | Trạng thái xác nhận và định danh bản ghi theo quyền. |
| Đã đăng ký trước đó | Không tạo bản ghi trùng; trả trạng thái phù hợp. |
| Hết chỗ | Không lưu đăng ký sai; phản hồi rõ. |
| Request gần đồng thời | Không xác nhận quá sức chứa, dữ liệu nhất quán. |
| Timeout sau khi server đã lưu | Không suy tự động là thất bại; có cơ chế tra/khôi phục trạng thái thật. |
| Gọi API trái quyền | Server từ chối, không lộ dữ liệu. |

Một số hành vi có thể được mô tả bằng Gherkin:

~~~gherkin
Feature: Đăng ký khóa học miễn phí giữa nhiều thành phần

  Scenario: Học viên đăng ký thành công
    Given học viên A đã xác thực và đủ điều kiện cho khóa X
    And khóa X còn ít nhất một chỗ
    When A gửi yêu cầu đăng ký khóa X
    Then hệ thống lưu đúng một đăng ký hiệu lực cho A
    And giao diện hiển thị kết quả xác nhận tương ứng

  Scenario: Hai học viên tranh chỗ cuối
    Given khóa X còn đúng một chỗ
    When hai học viên đủ điều kiện gửi yêu cầu đồng thời
    Then tối đa một đăng ký mới được xác nhận
    And số đăng ký hiệu lực không vượt sức chứa

  Scenario: Học viên cố xem thông tin người khác
    Given học viên B không có quyền xem đăng ký riêng của A
    When B yêu cầu thông tin đăng ký của A qua API
    Then hệ thống từ chối truy cập
    And không trả dữ liệu đăng ký riêng của A

  Scenario: Gửi lại sau khi mất phản hồi
    Given yêu cầu đăng ký ban đầu của A đã lưu thành công
    And A không nhận được phản hồi mạng
    When A gửi lại cùng yêu cầu hoặc tra trạng thái theo cơ chế đã định
    Then không có đăng ký hiệu lực thứ hai của A cho cùng khóa
    And A có thể biết trạng thái thật
~~~

Những ví dụ này giúp **nhiều nhóm hiểu chung tiêu chuẩn**, nhưng chưa tự động là test chạy được. Cần triển khai contract/integration/end-to-end tests phù hợp với hệ thống và quyền.

### 17.3. Bước 3 — Thống nhất quyền và dữ liệu từ sớm

Enrollment và Identity xác nhận:

- Token/claim nào đáng tin và nơi kiểm tra xác thực.
- Kiểm tra phân quyền ở server, không chỉ ẩn UI.
- Cơ chế user identity cho database lookup.
- Trường dữ liệu nào consumer được phép thấy.
- Test từ chối trái quyền và kịch bản token không hợp lệ.

Không cần chờ Identity viết lại dịch vụ nếu API hiện tại đã đáp ứng; đôi khi **trao đổi hợp đồng và test** là đủ để gỡ D-02.

### 17.4. Bước 4 — Giảm chờ ở Platform

Platform và Enrollment cùng định nghĩa môi trường thử:

| Điều kiện | Minh chứng cần có |
| --- | --- |
| Dữ liệu test không dùng hồ sơ học viên thật trái phép. | Chính sách và cơ chế tạo dữ liệu phù hợp. |
| Có thể tái hiện tranh chỗ cuối. | Test đồng thời chạy được với DB và transaction tương ứng. |
| Quyền runner được giới hạn. | Pipeline chỉ có quyền cần thiết; không lộ secrets. |
| Có khả năng khởi tạo/thu hồi môi trường. | Template và hướng dẫn self-service hợp lệ. |
| Kết quả test liên kết tới version. | CI run/commit/version rõ, có thể điều tra lỗi. |

Nếu chỉ một phép thử cần quyền đặc biệt, không nên cấp quyền production cho tất cả Developers. Thay vào đó xây **một luồng cấp quyền, template hoặc hỗ trợ chuyên biệt có thời gian phản hồi rõ**.

### 17.5. Bước 5 — Tích hợp theo các thay đổi nhỏ

Một chuỗi thay đổi kỹ thuật an toàn:

1. Cập nhật hợp đồng và test mẫu giữa Journey–Enrollment.
2. Tạo endpoint đọc trạng thái từ dữ liệu hợp lệ và quyền phù hợp.
3. Thêm hành vi ghi đăng ký cùng ràng buộc không trùng, transaction và test tích hợp.
4. Kết nối UI với API thật, kiểm tra hành vi hết chỗ và request lặp.
5. Kiểm thử các đường rủi ro, quyền và concurrency trên bản tích hợp.
6. Chỉ mở khả năng cho người dùng khi tiêu chí chất lượng và release policy đạt.

Các PR có thể merge trước khi toàn tính năng được phát hành **nếu không phá đường sử dụng hiện tại và được cô lập an toàn**. Nhưng không được gọi tính năng chưa đáp ứng DoD là Increment hoàn tất chỉ vì có code đã merge hoặc một feature flag tắt.

### 17.6. Bước 6 — Theo dõi theo mục tiêu thay vì theo số task cục bộ

Nhóm có thể xem bảng:

| Câu hỏi | Chỉ báo hữu ích |
| --- | --- |
| Có **hành trình người dùng đầu cuối** chạy trên bản tích hợp chưa? | Một test/smoke test xuyên Web–Enrollment–Identity–DB. |
| Phụ thuộc nào đang thực sự chặn Done? | Thẻ blocked có owner, tuổi chờ và điều kiện gỡ. |
| Các hợp đồng có ổn định không? | Contract test và số vòng thay đổi gây rework. |
| Hành vi dữ liệu có đúng không? | Integration/concurrency tests và quan sát dữ liệu nhất quán. |
| Có thể rollout/khôi phục an toàn không? | Runbook, quyền, kiểm tra sau deploy và kế hoạch xử lý side effects. |
| Học viên có đạt kết quả không? | Phản hồi thực tế và tỷ lệ hoàn tất tác vụ khi được phép đo. |

Một Dashboard có “nhóm A 95% task, nhóm B 90% task” **không trả lời** liệu người học có thể đăng ký thành công hay không.

## 18. Khi phụ thuộc bị chặn hoặc thay đổi giữa chừng

### 18.1. Tình huống: hợp đồng Identity thay đổi

Giả sử Identity thông báo sẽ thay cấu trúc claim trong token. Enrollment có thể cần sửa phân quyền; Journey lo lỗi đăng nhập. Nhóm nên:

1. Đánh giá ngay những consumer/version bị ảnh hưởng.
2. Xem hợp đồng cũ có thể tiếp tục được hỗ trợ trong giai đoạn chuyển tiếp không.
3. Tạo test cho cả kịch bản hợp lệ và từ chối trái quyền.
4. Đưa ra lộ trình tương thích và dự báo rủi ro.
5. Tránh triển khai thay đổi phá tương thích đột ngột khi các consumer chưa sẵn sàng.
6. Cập nhật điều kiện Done/release và runbook nếu cần.

Không được giữ token cũ không an toàn chỉ để “không bị phụ thuộc”; có những thay đổi bảo mật phải triển khai theo hướng dẫn khẩn cấp. Khi ấy ưu tiên an toàn, phối hợp theo quy trình có thẩm quyền và truyền thông tác động.

### 18.2. Tình huống: Platform không cấp được môi trường DB tích hợp

Không nên chọn một trong hai cực:

- **Cực 1:** “Chúng ta sẽ báo Done dù test concurrency chưa chạy.”
- **Cực 2:** “Mọi người chỉ ngồi chờ; không có gì khác có thể làm.”

Cách xử lý hợp lý:

- Ghi rõ **điều gì bị chặn và vì sao**.
- Tìm khả năng tự phục vụ/template hợp lệ hoặc người dự phòng.
- Đẩy các kiểm tra cục bộ/contract có thể làm sớm, nhưng **không đánh tráo chúng thành bằng chứng tích hợp**.
- Thảo luận lại thứ tự công việc và cách tập trung người hỗ trợ.
- Nếu không thể đạt DoD đúng hạn, công khai dự báo và điều chỉnh phạm vi/mốc theo quyền; không hạ chuẩn bắt buộc.

### 18.3. Tình huống: đối tác bên ngoài trễ

Nếu dịch vụ thông báo của đối tác trễ, cần xét liệu **email xác nhận có bắt buộc cho lát cắt đang giao không**:

- Nếu không bắt buộc trong phạm vi đã thống nhất, có thể tách khả năng gửi email thành hạng mục sau; giao trạng thái chính xác qua UI khi đạt DoD.
- Nếu bắt buộc về nghiệp vụ hoặc pháp lý, cần quản lý phụ thuộc như điều kiện hoàn tất, có phương án fallback hợp lệ và truyền thông rủi ro.
- Nếu có hợp đồng/mock, có thể xây các phần còn lại sớm nhưng phải **kiểm tra tích hợp thật** trước khi tuyên bố chức năng phụ thuộc đối tác Done.

Điều quan trọng là **không gọi việc bỏ một điều kiện bắt buộc là “Agile thích ứng”**.

### 18.4. Hướng dẫn ứng phó cho một blocker

~~~mermaid
flowchart TD
    A["Phát hiện item bị chặn"] --> B["Xác nhận phụ thuộc và hậu quả"]
    B --> C{"Có thể loại bỏ / thu hẹp an toàn?"}
    C -- "Có" --> D["Chia lát cắt, hợp đồng hoặc self-service"]
    C -- "Không" --> E["Đưa owner và bên cung cấp cùng ra quyết định"]
    D --> F["Kiểm chứng đầu ra trên bản tích hợp"]
    E --> G{"Cần thẩm quyền / công suất khác?"}
    G -- "Có" --> H["Escalation với lựa chọn và tác động"]
    G -- "Không" --> F
    H --> F
    F --> I{"Đạt điều kiện cần?"}
    I -- "Chưa" --> B
    I -- "Có" --> J["Tiếp tục PBI, cập nhật dự báo và bài học"]
~~~

Sơ đồ không cho phép bỏ qua sự cố dữ liệu/bảo mật. Khi có tác động tới người dùng hoặc nghĩa vụ khẩn, cần **ứng cứu theo chính sách tương ứng** trước khi chỉ xử lý như blocker backlog thông thường.

### 18.5. Gỡ phụ thuộc nhưng không đẩy rủi ro sang nhóm khác

Một “giải pháp” giảm chờ của Journey bằng cách yêu cầu Enrollment làm thêm mọi thay đổi UI-related cho tất cả consumer có thể **dịch chuyển WIP và nghẽn** thay vì cải thiện toàn hệ thống. Nhóm cần xem:

- Thời gian từ nhu cầu tới Increment **toàn luồng** có giảm không?
- Lượng rework/công việc support có tăng ở phía provider không?
- Số lần thay đổi API phá tương thích có giảm không?
- Người dùng có nhận giá trị sớm và đúng hơn không?
- Tải và trực sự cố của các đội có bền vững không?

**Giảm phụ thuộc thực sự** cần cải thiện flow và chất lượng chung, không chỉ báo cáo tiến độ của một đội.

## 19. Đo lường tác động của việc giảm phụ thuộc

### 19.1. Chọn thước đo cho vấn đề đã quan sát

| Metric | Định nghĩa tham khảo | Câu hỏi |
| --- | --- | --- |
| **Blocked time** | Thời gian item không thể tiến triển vì điều kiện được ghi nhận, theo cách tính chung. | Chờ nhóm khác chiếm bao nhiêu trong cycle time? |
| **Dependency age** | Thời gian từ khi phụ thuộc được ghi hoặc trở thành blocker tới hiện tại/giải quyết. | Phụ thuộc nào đang tồn đọng quá lâu? |
| **Cross-team handoffs** | Số lần chuyển giao quyền xử lý/đầu ra theo quy ước. | Có nhiều cổng không tạo giá trị không? |
| **Cycle time** | Thời gian Started → Finished của hạng mục hoàn tất. | Giá trị mất bao lâu để hoàn thành xuyên qua các nhóm? |
| **Work item age** | Tuổi hạng mục đang dở. | Item nào bị mắc kẹt dù throughput chung có vẻ tốt? |
| **WIP và throughput** | Việc đang dở và số item hoàn tất trong khoảng đo. | Có tích lũy hàng đợi khi mỗi nhóm tối đa hóa độ bận? |
| **Integration failure rate** | Số/tỷ lệ bản tích hợp có lỗi theo định nghĩa đã thống nhất. | Các hợp đồng và kiểm thử có phát hiện sai khác đủ sớm? |
| **Lead time for change** | Thời gian từ mốc thay đổi chọn đến khi triển khai theo quy ước. | Phụ thuộc có kéo dài khả năng đưa thay đổi ra dùng? |
| **Rework** | Công việc phải sửa do hiểu sai/phụ thuộc thay đổi, theo cách nhận diện. | Việc làm rõ hợp đồng sớm có giảm làm lại? |
| **Outcome người dùng** | Tác vụ hoàn tất, lỗi đăng ký, hỗ trợ cần thiết, trải nghiệm thực. | Giảm chờ có tạo giá trị hay chỉ giảm thủ tục? |

Các metric chỉ có ý nghĩa khi **mốc, đơn vị, phạm vi và chất lượng dữ liệu** được ghi rõ. Không dùng số dependency đã đóng hoặc số PR mỗi cá nhân làm KPI thay thế giá trị.

### 19.2. So sánh trước–sau có guardrails

Giả sử nhóm thử ký hợp đồng API sớm và cấp môi trường tự phục vụ, quan sát hai giai đoạn minh họa:

| Chỉ số | Trước cải tiến | Sau cải tiến |
| --- | ---: | ---: |
| Số PBI cùng loại hoàn tất trong kỳ | 10 | 11 |
| Cycle time trung vị | 12 ngày | 8 ngày |
| Thời gian blocked trung vị do phụ thuộc | 5 ngày | 2 ngày |
| Rework vì lệch API contract | 4 trường hợp | 1 trường hợp |
| Lỗi nghiêm trọng sau phát hành | 0 | 0 |

Đây là **dữ liệu giả để luyện cách đọc**. Có tín hiệu cải thiện flow và ít sửa lại vì hợp đồng, nhưng chưa thể khẳng định **cải tiến đã gây ra toàn bộ chênh lệch**:

- Hai tập PBI có cùng loại, quy mô và rủi ro không?
- Có sự cố môi trường hoặc kỳ nghỉ ở giai đoạn nền không?
- Bằng chứng lỗi có được thu đủ lâu sau release không?
- Điều kiện Finished/DoD và cách ghi blocked có thay đổi không?
- Có chuyển công việc sang team Platform hoặc support mà chưa được tính không?

Không có lỗi nghiêm trọng quan sát trong mẫu nhỏ **không đồng nghĩa chứng minh không có rủi ro**.

### 19.3. Tính tỷ lệ thời gian chờ minh họa

Ví dụ một PBI mất **9 ngày** từ Started đến Done; hai khoảng chờ không chồng lấn là **3 ngày** chờ API contract và **2 ngày** chờ môi trường:

\[
\text{Tỷ lệ chờ minh họa}
=\frac{3+2}{9}\times 100\%
\approx55{,}6\%.
\]

Nếu giảm phần chờ từ **5 xuống 2 ngày**, trong khi các khoảng khác giữ nguyên, tổng thời gian **theo giả định đơn giản** có thể từ 9 xuống 6 ngày. Nhưng thực tế có thể phát sinh rework, việc chồng lấn, queue khác hoặc tăng khối lượng nên **không hứa chắc giảm đúng ba ngày**.

### 19.4. Lead indicator và lag indicator

- **Leading signals:** hợp đồng được làm rõ trước code, dependency age thấp hơn, review waiting time giảm, test tích hợp chạy sớm hơn.
- **Lagging outcomes:** cycle time giảm bền vững, ít lỗi hậu tích hợp, các Increment đáp ứng DoD sớm hơn, người dùng hoàn tất tác vụ tốt hơn.

Một thay đổi có thể cải thiện lead indicator nhưng chưa đủ thời gian để thấy outcome. Nhóm nên ghi điều đã biết và chờ thêm bằng chứng, thay vì tuyên bố thành công sớm.

### 19.5. Đo hệ thống, không ép mọi nhóm giống nhau

Nếu mỗi nhóm đo cycle time bằng một workflow khác nhau, không thể **cộng trung bình** rồi gọi đó là “thời gian hoàn tất sản phẩm” mà không có ranh giới nhất quán. Có thể đo **đầu–cuối của một lát cắt giá trị**, đồng thời dùng các metrics cục bộ để tìm nơi chờ.

Mục tiêu là tìm **nút thắt có thể cải thiện**, không xếp hạng nhóm Web với Platform hoặc đổ lỗi người giữ dependency già nhất.

## 20. Những tình huống cần cân nhắc khi nhiều sản phẩm và tổ chức cùng liên quan

### 20.1. Một sản phẩm nhiều Scrum Team khác nhiều sản phẩm có API chung

Hai trường hợp dễ bị nhầm:

| Tình huống | Định hướng phối hợp |
| --- | --- |
| **Nhiều Scrum Team làm một sản phẩm** | Hướng tới Product Goal, Product Backlog, Product Owner và Definition of Done chung như Scrum Guide mô tả; tích hợp theo tiêu chuẩn sản phẩm. |
| **Nhiều sản phẩm độc lập tiêu thụ một dịch vụ chung** | Các backlog/PO theo ranh giới sản phẩm riêng; cần contract, chính sách thay đổi, công suất, đường xử lý và ưu tiên liên sản phẩm minh bạch. |

Nếu cùng một đơn vị kinh doanh có nhiều thương hiệu hoặc sản phẩm, **không tự suy ra chỉ có một Product Owner cho mọi thứ**. Cần xác định **sản phẩm thật** dựa trên giá trị, người dùng, trách nhiệm và quyết định phát triển/vận hành.

### 20.2. Phụ thuộc vào đối tác ngoài quyền quản lý trực tiếp

Đối tác cung cấp API xác thực, thanh toán hoặc thông báo có thể thay đổi dịch vụ với nhịp khác. Nhóm không thể đơn giản “yêu cầu họ dự Sprint Planning”.

Biện pháp phù hợp:

- Dùng hợp đồng và chính sách version/deprecation đã thỏa thuận.
- Có môi trường thử, account test và dữ liệu an toàn được cấp hợp lệ.
- Giám sát tín hiệu nhà cung cấp và khả năng chuyển tuyến.
- Thử failure modes phù hợp, chẳng hạn timeout, retry, unavailable.
- Có phương án fallback khi được phép và an toàn.
- Ghi rõ giới hạn SLA/điều khoản, không tự hứa thay đối tác.
- Cân nhắc rủi ro tập trung vào một nhà cung cấp nếu hậu quả lớn.

Tăng số meeting trong nội bộ **không khắc phục được API đối tác không ổn định**; cần giảm coupling và có cách phát hiện/khôi phục.

### 20.3. Phụ thuộc bảo mật/pháp lý bắt buộc

Một số thay đổi liên quan dữ liệu cá nhân, quyền truy cập, thanh toán hoặc tuân thủ cần đánh giá theo chính sách. Giảm phụ thuộc không đồng nghĩa bỏ những quyết định được quy định.

Có thể cải thiện:

1. Đưa chuyên gia vào sớm ở bước thiết kế, không mời ở ngày cuối.
2. Chuẩn hóa những trường hợp thường gặp và tiêu chí xét duyệt.
3. Tự động hóa phép kiểm tra **được phép** và giữ log truy vết.
4. Có hướng dẫn để nhóm chuẩn bị đủ đầu vào trước khi yêu cầu.
5. Dự báo công suất và có người dự phòng có thẩm quyền.

Đừng đổi **rủi ro không thể chấp nhận** lấy chỉ số lead time ngắn. Khi có incident gây hại, dùng đường ứng cứu có thẩm quyền thay vì chờ vòng sắp thứ tự backlog thường lệ.

### 20.4. Phụ thuộc múi giờ và làm việc phân tán

Khi các nhóm làm ở các múi giờ khác nhau:

- Ghi contract, quyết định và tiêu chí kiểm chứng ở nơi tra cứu được.
- Có đầu mối và khoảng thời gian liên lạc chồng lấn hợp lý.
- Phân biệt việc cần trao đổi đồng bộ với việc có thể async.
- Có chính sách phản hồi theo mức khẩn và người dự phòng.
- Không biến lệch múi giờ thành yêu cầu một nhóm trực đêm mãi.
- Dùng CI/contract tests để giảm nhu cầu xác nhận thủ công vào một khung giờ.

**Tài liệu hóa giúp trao đổi bất đồng bộ**, nhưng nếu phụ thuộc là một quyết định khó và nhiều giả định xung đột, một buổi trao đổi ngắn đúng người có thể rẻ hơn hàng chục tin nhắn.

### 20.5. Phụ thuộc sau bàn giao và khôi phục sự cố

Luồng giá trị chưa kết thúc ở merge hoặc deployment. Khi có sự cố:

- Support cần biết phiên bản, giới hạn và cách xác minh người dùng an toàn.
- On-call cần dashboard, runbook, quyền và đầu mối Developers.
- Nhóm quản lý dữ liệu cần biết cách sửa/khôi phục có truy vết.
- Product Owner cần tín hiệu outcome và rủi ro để điều chỉnh backlog.

Nếu một sản phẩm không thể được hỗ trợ khi nhóm phát triển kết thúc Sprint, tổ chức đã tạo **phụ thuộc vận hành chưa được giải quyết**. Release readiness, observability, kế hoạch khôi phục và tri thức hỗ trợ cần được xây vào cách làm.

## 21. Những phản mẫu phổ biến

| Phản mẫu | Hậu quả | Điều chỉnh |
| --- | --- | --- |
| **Chia mọi backlog item theo frontend/backend/QA** | Nhiều “Done cục bộ” nhưng không có Increment dùng được. | Bắt đầu bằng lát cắt dọc giá trị, tích hợp và test sớm. |
| **Chỉ lập danh sách team A chờ team B** | Biết có phụ thuộc nhưng không có điều kiện gỡ. | Thêm consumer/provider, đầu ra, owner, tác động, mốc kiểm chứng. |
| **Vẽ đồ thị một lần rồi coi là bất biến** | Không phản ánh API, ưu tiên và rủi ro mới. | Cập nhật theo thay đổi quan trọng, loại bỏ cạnh đã giải quyết. |
| **Đếm số phụ thuộc được đóng để báo năng suất** | Khuyến khích chia ticket giả hoặc đóng sớm chưa tích hợp. | Đo thời gian chờ, chất lượng và outcome toàn luồng. |
| **Họp liên nhóm thật đông nhưng thiếu quyết định** | Tốn thời gian mà blocker còn nguyên. | Chỉ mời bên có thông tin/quyền, chốt quyết định và kiểm chứng. |
| **Chờ cuộc họp tuần mới trao đổi lệch API** | Lỗi tích hợp phát hiện muộn. | Kênh trực tiếp, contract tests và review sớm. |
| **Mock xanh được coi là tích hợp Done** | Provider thật có thể không tương thích. | Chạy contract/integration tests trên bản thực trước khi Done. |
| **Mọi API thay đổi bắt consumer deploy đồng thời** | Release coupling, khó rollback. | Hợp đồng tương thích, chuyển tiếp và quản lý version. |
| **Một chuyên gia duyệt mọi thay đổi** | Hàng đợi, single point of failure. | Pairing, người dự phòng hợp lệ, tiêu chuẩn và tự động hóa nơi phù hợp. |
| **Tự phục vụ bằng cách cấp quyền rộng không kiểm soát** | Rủi ro bảo mật, dữ liệu và chi phí. | Template có guardrails, phân quyền, audit và hỗ trợ ngoại lệ. |
| **Tăng WIP để ai cũng bận** | Nhiều queue, cycle time dài, đổi ngữ cảnh. | Tập trung hoàn tất, kiểm soát WIP, gỡ blocker. |
| **Ẩn thẻ blocked khỏi workflow** | Metrics đẹp giả, item già bị bỏ quên. | Giữ trạng thái rõ, đo tuổi và thời gian chờ. |
| **Gộp các ước lượng riêng rồi hứa ngày giao chắc chắn** | Bỏ qua bất định, rework và integration. | Dự báo có giả định, thử sớm, kiểm chứng tiến độ tới giá trị. |
| **Mỗi Scrum Team tự có Product Goal/PO/DoD riêng cho cùng một sản phẩm** | Mất định hướng/chất lượng chung, sai thiết kế Scrum cho một sản phẩm. | Tuân thủ các điều kiện nhiều Scrum Team cùng sản phẩm. |
| **Dùng Scrum of Scrums như hội nghị báo cáo** | Đếm tiến độ, không giảm phụ thuộc thật. | Tập trung blockers, integration và quyết định cụ thể. |
| **Đánh dấu Done trước khi kiểm thử quyền hoặc dữ liệu** | Có thể tạo Increment sai, gây rủi ro người dùng. | Giữ DoD và phép kiểm chứng bắt buộc. |
| **Đổi architecture chỉ để giảm số cạnh dependency** | Tăng độ phức tạp runtime, vận hành và dữ liệu. | Xem tổng chi phí/coupling và khả năng self-service. |
| **Mỗi nhóm tối ưu velocity riêng** | Dễ tối đa task cục bộ mà giá trị chưa tới người dùng. | Đo flow/outcome xuyên nhóm, giữ thước đo chất lượng. |
| **Escalation chỉ là thêm cấp quản lý vào email** | Không có người quyết hoặc lựa chọn hành động. | Nêu tác động, quyết định cần đưa ra, owner, phương án. |
| **Bỏ phụ thuộc bắt buộc vì muốn “Agile nhanh”** | Vi phạm chất lượng, bảo mật, pháp lý. | Đưa thẩm quyền vào sớm, tự động hóa hợp lệ, không bỏ chuẩn. |
| **Revert mã được coi rollback dữ liệu hoàn chỉnh** | Schema/message/email và side effects có thể vẫn tồn tại. | Kế hoạch phục hồi dữ liệu, tương thích và kiểm chứng sau rollback. |
| **Không có ai theo dõi cải tiến sau khi gỡ blocker** | Phụ thuộc lặp lại trong nhiều Sprint. | Hậu kiểm và thử cải tiến hệ thống có owner và metric. |

## 22. Lộ trình áp dụng cho một tổ chức có nhiều nhóm

### Bước 1 — Chọn một hành trình giá trị cụ thể

Đừng bắt đầu bằng bản đồ mọi dịch vụ trong doanh nghiệp. Chọn một hành trình có giá trị và nhiều vòng chờ thấy được, chẳng hạn **học viên tự đăng ký khóa**. Đặt ranh giới rõ: từ lúc một PBI được bắt đầu đến khi Increment đạt điều kiện sử dụng đã định.

### Bước 2 — Quan sát workflow thật

Xem lịch sử PBI, PR, CI, review, integration, deployment và phản hồi support. Hỏi người trực tiếp làm. Ghi **khoảng chờ, người quyết và nguyên nhân thực**; tránh kết luận chỉ dựa vào sơ đồ tổ chức.

### Bước 3 — Lập bản đồ phụ thuộc tối giản

Với 3–6 phụ thuộc ảnh hưởng nhiều nhất, ghi:

- Bên cần và bên cung cấp.
- Đầu ra/điều kiện kiểm chứng.
- Rủi ro và mốc cần.
- Owner trao đổi, phương án giảm phụ thuộc.

Nếu xuất hiện vòng phụ thuộc, ưu tiên một **buổi làm rõ hợp đồng/định nghĩa hành vi** trước khi tiếp tục ước lượng.

### Bước 4 — Phân loại: loại bỏ, giảm hay điều phối?

| Lựa chọn | Khi nên dùng | Ví dụ |
| --- | --- | --- |
| **Loại bỏ** | Phụ thuộc do cấu trúc/cổng thừa, không bắt buộc. | Nhóm sản phẩm được tạo môi trường test qua template an toàn. |
| **Giảm** | Phụ thuộc vẫn có nhưng có thể thu nhỏ/tăng tự chủ. | Hợp đồng API ổn định, kiểm thử tự động, chuyển schema từng bước. |
| **Điều phối** | Ràng buộc an toàn, chuyên môn hoặc đối tác không thể bỏ. | Review bảo mật có chuẩn đầu vào và người có quyền rõ. |

Không chỉ “điều phối cho tốt hơn” một phụ thuộc tồn tại nhiều năm nếu có thể **thay đổi thiết kế công việc để không phải chờ thường xuyên nữa**.

### Bước 5 — Thử một thay đổi nhỏ

Ví dụ:

- Chốt contract bằng ví dụ và test trước khi hai nhóm bắt đầu code.
- Cho một nhóm dùng môi trường test self-service có quyền giới hạn.
- Làm một lát cắt dọc đa chuyên môn thay vì ba PBI theo lớp.
- Chỉ định reviewer dự phòng đủ quyền cho loại thay đổi thường gặp.

Chọn **một giả thuyết có khả năng kiểm chứng** thay vì cùng lúc đổi toàn bộ kiến trúc và cơ cấu tổ chức.

### Bước 6 — Đo tác động toàn luồng

Có thể theo dõi:

- Thời gian blocked tại phụ thuộc đã chọn.
- Cycle time và work item age của PBI liên quan.
- Rework vì sai contract.
- Lỗi trên bản tích hợp hoặc sau release.
- Tải công việc của nhóm cung cấp và outcome người dùng.

Nếu một metric tốt hơn nhưng lỗi dữ liệu tăng, phải ưu tiên chất lượng và an toàn. Nếu không thấy cải thiện, điều chỉnh giả thuyết thay vì đổ lỗi người phối hợp.

### Bước 7 — Chuẩn hóa và tiếp tục cải tiến

Những thử nghiệm có tác dụng có thể trở thành:

- Working agreement/Definition of Workflow mới.
- Contract tests hoặc policy versioning.
- Template self-service.
- Điều kiện chất lượng chung và kế hoạch tích hợp.
- Runbook/đường escalation.
- Thay đổi ranh giới quyền sở hữu khi có đủ bằng chứng.

Theo dõi khi sản phẩm/nhân sự/quy mô đổi. Cách tổ chức giảm phụ thuộc hôm nay có thể thành nút thắt mới khi lượng consumer tăng.

## 23. Bài tập thực hành và đáp án gợi ý

### Bài tập 1 — Phân biệt phụ thuộc và hợp tác

Xét năm tình huống:

1. Web và Enrollment cùng thảo luận mã trạng thái cho API mới.
2. Web không thể kiểm chứng hành vi vì API chưa có hợp đồng thống nhất.
3. Một thay đổi bảo mật bắt buộc cần người có thẩm quyền xem xét.
4. Nhiều PBI chờ môi trường staging bị hỏng.
5. Support góp ý thông báo “đăng ký thành công” cần rõ hơn.

**Yêu cầu:** xác định đâu là hợp tác, phụ thuộc, ràng buộc bắt buộc hay blocker; giải thích vì sao một tình huống có thể thuộc nhiều nhóm.

**Gợi ý:** (1) là hợp tác, nếu thiếu quyết định có thể trở thành phụ thuộc; (2) là phụ thuộc hợp đồng đang cản kiểm chứng; (3) là điều kiện kiểm soát bắt buộc và có thể tạo hàng đợi cần quản lý đúng quyền; (4) là blocker môi trường thực; (5) là phản hồi/cộng tác sản phẩm, chưa chắc là blocker. Không đánh dấu mọi tương tác giữa hai nhóm thành “rủi ro nghiêm trọng”.

### Bài tập 2 — Đọc sơ đồ phụ thuộc có hướng

Sử dụng quy ước **A → B nghĩa là A cần đầu ra từ B**. Có các cạnh:

- Web → Enrollment.
- Enrollment → Identity.
- Enrollment → Platform.
- Identity → Platform.

**Câu hỏi:**

1. Nhóm nào phụ thuộc trực tiếp vào Identity?
2. Web có thể chịu ảnh hưởng gián tiếp nếu Platform bị chặn không?
3. Cạnh nào đáng xem lại để giảm thời gian chờ?
4. Một đường phụ thuộc dài có tự chứng minh một nhóm là nút thắt không?

**Gợi ý:** Enrollment trực tiếp cần Identity. Web có thể chịu tác động gián tiếp qua Enrollment và Identity/Platform. Cần dữ liệu hàng đợi, tác động, khả năng self-service và chất lượng để biết cạnh nào cần giảm. Số cạnh lớn không tự chứng minh có nút thắt; một phụ thuộc ổn định có contract rõ có thể ít tốn kém.

### Bài tập 3 — Viết dependency register đủ hành động

Tình huống: nhóm Journey phải chờ nhóm Identity xác nhận cách ánh xạ quyền xem lịch sử đăng ký. Chưa biết ai có quyền ra quyết định; PBI đã chờ ba ngày.

**Yêu cầu:** viết một thẻ dependency có:

- Consumer và provider.
- Điều kiện cần có và tiêu chí xác minh.
- Rủi ro tới Sprint Goal/DoD.
- Một owner theo dõi và một người cần quyết định.
- Hành động tiếp, mốc kiểm tra, phương án giảm chờ.

**Gợi ý:** “Cần xác nhận claim/permission nào cho người dùng đọc lịch sử đăng ký của chính mình; phải có test từ chối khi đọc người khác”. Không ghi “Identity làm xong phần quyền” chung chung. Có thể phối hợp ngắn với owner Identity, viết contract/policy test và quyết định được ghi lại.

### Bài tập 4 — Tháo vòng phụ thuộc

Team A phát triển frontend chờ Team B chốt response schema. Team B chờ Team A cung cấp thiết kế màn hình để biết cần trường gì. Cả hai báo “đang chờ team khác” trong ba buổi họp.

**Câu hỏi:** xác định vòng phụ thuộc, đề xuất cách tháo bằng một buổi làm rõ và mô tả kiểm chứng trước khi mỗi nhóm tiếp tục.

**Gợi ý:** cần một cuộc làm rõ giữa bên hiểu hành vi, frontend, provider và kiểm thử; thống nhất ví dụ thành công/hết chỗ/lặp yêu cầu, hợp đồng tối thiểu và test phù hợp. Hai nhóm có thể làm song song với stub contract, sau đó chạy contract/integration tests trên bản thực. Không cần chờ toàn bộ UI hoặc toàn bộ API xong mới quyết định.

### Bài tập 5 — Chọn lát cắt dọc có giá trị và vẫn an toàn

Có các task:

- Thiết kế màn hình đăng ký.
- Tạo API lưu đăng ký.
- Thay bảng enrollment.
- Tích hợp xác thực.
- Kiểm thử hai người giành chỗ cuối.
- Viết thông báo email.

**Yêu cầu:** xây một lát cắt có thể sử dụng cho học viên đăng ký khóa miễn phí. Những gì có thể hoãn **nếu** Product Owner xác nhận không phải điều kiện bắt buộc? Những gì không được bỏ?

**Gợi ý:** có thể cần UI, API, DB, quyền, thử request lặp/đồng thời và thông báo kết quả trong giao diện để tạo Increment đăng ký đáng tin cậy. Email có thể tách nếu không thuộc yêu cầu/điều kiện bắt buộc. Không được bỏ phân quyền, nhất quán dữ liệu hoặc DoD để báo Done sớm.

### Bài tập 6 — Scrum nhiều nhóm cùng một sản phẩm

Ba Scrum Team cùng phát triển một sản phẩm nền tảng học trực tuyến. Mỗi nhóm hiện có một Product Backlog, Product Owner và DoD riêng. Kết quả: web báo Done, API báo Done nhưng luồng đăng ký trên bản tích hợp chưa hoạt động.

**Câu hỏi:**

1. Theo Scrum Guide 2020, cần điều chỉnh những điểm nào khi đúng là cùng một sản phẩm?
2. Tại sao ba bộ unit tests xanh không đủ?
3. Sprint Review nên xem gì?
4. Làm thế nào phối hợp mà không biến Daily Scrum thành họp báo cáo quản lý?

**Gợi ý:** cần **một Product Goal, một Product Backlog, một Product Owner và một DoD chung** cho cùng sản phẩm. Phải tạo và xem Increment thực sự tích hợp, đáp ứng DoD; các đội phối hợp bằng trao đổi trực tiếp, contract tests, integration tests và hoạt động điều phối cần thiết; Daily Scrum vẫn phục vụ Developers kiểm tra hướng Sprint Goal.

### Bài tập 7 — Đánh giá việc giảm phụ thuộc về hạ tầng

Team Platform nhận 40 yêu cầu tạo môi trường test giống nhau mỗi tháng. Mỗi yêu cầu cần người trực xử lý thủ công, thường chờ hai ngày. Có hai đề xuất:

- A. Tạo template self-service với quyền giới hạn, dữ liệu test giả, audit và quota.
- B. Cấp cho mọi Developer quyền admin production để tự làm nhanh.

**Yêu cầu:** chọn cách thử phù hợp, ghi một metric chính và ít nhất hai guardrails.

**Gợi ý:** A thường là hướng có khả năng giảm phụ thuộc lặp; đo thời gian từ yêu cầu tới môi trường có thể dùng. Guardrails gồm quyền, chi phí, tách dữ liệu, lỗi cấu hình và khả năng thu hồi môi trường. B không phù hợp vì tăng rủi ro đáng kể chỉ để giảm hàng đợi.

### Bài tập 8 — Tính phần thời gian chờ

Một PBI có:

- 2 ngày phát triển.
- 3 ngày chờ API contract.
- 1 ngày sửa và tích hợp.
- 2 ngày chờ môi trường kiểm thử.
- 1 ngày kiểm chứng cuối.

Các khoảng được giả định **không chồng lấn**.

**Yêu cầu:** tính cycle time, phần thời gian chờ và tỉ lệ chờ. Nếu giảm chờ API từ ba xuống một ngày, những yếu tố nào khiến tổng cycle time không chắc giảm đúng hai ngày?

**Gợi ý:**

\[
\text{Cycle time}=2+3+1+2+1=9\text{ ngày}.
\]

\[
\text{Waiting fraction}=\frac{3+2}{9}\times100\%\approx55{,}6\%.
\]

Theo mô hình tĩnh, giảm hai ngày chờ có thể rút tổng còn 7 ngày nếu mọi khoảng khác giữ nguyên. Thực tế có thể có rework, phụ thuộc mới, chồng lấn công việc, thay đổi điều kiện DoD hoặc lỗi môi trường; cần quan sát thay vì cam kết chắc.

### Bài tập 9 — Contract test và integration test

Journey và Enrollment thống nhất hợp đồng API. Cả hai chạy contract tests xanh, nhưng khi hai học viên cùng đăng ký chỗ cuối, DB ghi hai bản ghi hiệu lực.

**Yêu cầu:** giải thích vì sao phụ thuộc API có thể đã giảm nhưng sản phẩm vẫn chưa Done. Đề xuất các kiểm chứng cần thiết.

**Gợi ý:** contract tests kiểm tra giao diện giữa consumer/provider, không tự chứng minh transaction và concurrency. Cần integration test trên DB phù hợp, kiểm tra quy tắc sức chứa, idempotency và hồi quy end-to-end. Không coi API tương thích đồng nghĩa toàn bộ hành vi an toàn.

### Bài tập 10 — Nhận diện cải tiến giả tạo từ dữ liệu flow

Sau một cải tiến, nhóm Journey báo cycle time của task frontend giảm 5 xuống 2 ngày, nhưng thời gian chờ tích hợp của toàn PBI tăng 4 lên 8 ngày. Nhóm Enrollment cũng báo đã tăng số task Done.

**Câu hỏi:** đánh giá này cho thấy gì? Nhóm nên thay đổi cách đo và cách phối hợp thế nào?

**Gợi ý:** từng nhóm có thể tối ưu cục bộ trong khi **lead time tới giá trị toàn luồng xấu đi**. Đo Started–Finished nhất quán cho PBI/Increment, xem dependency age, blocked time, WIP và chất lượng, giảm bàn giao không cần thiết bằng contract/lát cắt dọc. Không dùng task Done riêng để chứng minh outcome.

### Bài tập 11 — Nhà cung cấp ngoài tổ chức thay đổi API

Một dịch vụ Identity bên ngoài thông báo thay cấu trúc token trong hai tuần. Các nhóm Journey và Enrollment đang dùng API hiện hành, có người dùng production thật.

**Yêu cầu:** nêu một kế hoạch:

1. Xác nhận hợp đồng và những consumer bị ảnh hưởng.
2. Phân loại mức rủi ro bảo mật/tương thích.
3. Kiểm thử các phiên bản cùng tồn tại.
4. Thông báo người có quyền quyết định và support.
5. Chuẩn bị rollout/khôi phục khi có tác động dữ liệu.

**Gợi ý:** đánh giá hợp đồng và điều khoản nhà cung cấp, chạy contract/integration/auth tests, dùng cơ chế version/transition được cho phép, bảo vệ token/secret, không tự trì hoãn một vá bảo mật bắt buộc. Có đầu mối escalation và điều kiện dừng rõ, không chỉ ghi mốc vào lịch.

### Bài tập 12 — Khi nào đổi ranh giới nhóm?

Một nhóm sản phẩm phải gửi ticket sang ba nhóm khác cho gần mọi PBI. Trong sáu tháng, dependency age cao, nhiều ticket lặp, cùng các API tương đối ổn định. Người quản lý đề nghị sáp nhập tất cả nhóm thành một nhóm rất lớn.

**Yêu cầu:** nêu ba cách thử trước khi đổi toàn bộ cấu trúc tổ chức, cùng dữ liệu cần quan sát để biết liệu cần thay đổi ranh giới nhóm thật.

**Gợi ý:** thử self-service cho yêu cầu lặp; đưa năng lực/tài liệu vào nhóm dòng giá trị qua pairing/enabling; tạo hợp đồng và kiểm tra tự động; hoặc cùng thực hiện lát cắt dọc trong phạm vi hẹp. Đo blocked time, rework, throughput, chất lượng và tải nhóm cung cấp. Chỉ cân nhắc thiết kế lại nhóm với đủ bằng chứng về phụ thuộc lặp/chi phí nhận thức và khả năng vận hành.

### Bài tập 13 — Viết thông điệp escalation có thể hành động

Tình huống: PBI đăng ký bị chặn vì thiếu DB test môi trường. Viết một thông điệp tối đa 120 từ gửi người có quyền cấp môi trường.

Thông điệp cần nêu:

- Điều kiện cụ thể đang thiếu.
- Hậu quả đối với DoD/Sprint Goal.
- Thời điểm cần biết và mức bất định.
- Một phương án giảm chờ an toàn.
- Quyết định hoặc người hỗ trợ cần có.

**Ví dụ:**

> “Nhóm Enrollment chưa thể kiểm chứng trường hợp hai học viên tranh chỗ cuối vì môi trường DB test cách ly chưa được cấp. Đây là kiểm tra bắt buộc trước khi PBI đăng ký đạt DoD; nếu chưa có kết quả trong đợt tích hợp hiện tại, Sprint Goal có rủi ro. Chúng tôi đề xuất dùng template môi trường test đã được Platform cho phép, với dữ liệu giả và quyền giới hạn. Nhờ xác nhận đầu mối cấp quyền hoặc đề xuất phương án kiểm chứng tương đương an toàn. Chúng tôi sẽ cập nhật dự báo ngay khi biết phương án khả thi.”

Không biến escalation thành lời buộc tội một nhóm; giữ trách nhiệm và bằng chứng.

## 24. Checklist nhận diện và giảm phụ thuộc liên nhóm

### Khi làm rõ một mục tiêu hoặc PBI

- [ ] Mục tiêu được diễn đạt theo **giá trị/hành vi người dùng**, không chỉ task từng bộ phận.
- [ ] Có ranh giới sản phẩm và các quyền quyết định được hiểu rõ.
- [ ] Những năng lực cần thiết để tạo Increment dùng được đã được xác định.
- [ ] Các phụ thuộc API, dữ liệu, quyền, môi trường, chuyên môn, vận hành được xem xét theo rủi ro.
- [ ] Những người có quyền quyết định/hiểu phụ thuộc được mời làm rõ từ sớm.
- [ ] Các giả định về provider, hợp đồng và mức sẵn sàng được ghi rõ.
- [ ] Có cách chia lát cắt để giảm chờ mà vẫn giữ DoD và điều kiện an toàn.

### Khi ghi và theo dõi phụ thuộc

- [ ] Phụ thuộc ghi rõ **ai cần gì từ ai** và hạng mục/mục tiêu bị ảnh hưởng.
- [ ] Có đầu ra hoặc điều kiện **kiểm chứng được**.
- [ ] Có owner liên lạc và người có quyền ra quyết định khi cần.
- [ ] Có tác động, mốc cần biết, độ bất định và trạng thái thật.
- [ ] Phân biệt rủi ro có thể chặn với blocker đang xảy ra.
- [ ] Vòng phụ thuộc hoặc quyết định thiếu owner được xử lý sớm.
- [ ] Item đang chờ vẫn hiện trong WIP/work item age theo chính sách đo.
- [ ] Có phương án loại bỏ, giảm hoặc điều phối phụ thuộc phù hợp.

### Khi thiết kế kỹ thuật

- [ ] Hợp đồng giữa provider/consumer rõ, có ví dụ thành công/lỗi/biên.
- [ ] Có contract tests và integration tests tương xứng với rủi ro.
- [ ] Mock/stub được dùng đúng mục đích, không thay kiểm thử bản tích hợp.
- [ ] API/schema thay đổi theo lộ trình tương thích khi cần.
- [ ] Feature flags có quyền, owner và kế hoạch dọn, không thay phân quyền server.
- [ ] CI/mainline được kiểm chứng, không chỉ các nhánh riêng lẻ.
- [ ] Những thay đổi dữ liệu có kế hoạch migration và khôi phục đúng thẩm quyền.
- [ ] Self-service hạ tầng có giới hạn quyền, chi phí, dữ liệu và audit.
- [ ] Các dịch vụ dùng chung có owner, thông tin hợp đồng và đường hỗ trợ.

### Khi nhiều Scrum Team cùng một sản phẩm

- [ ] Cùng hướng tới một **Product Goal**, chia sẻ một Product Backlog và một Product Owner.
- [ ] Cùng Definition of Done cho một sản phẩm.
- [ ] Điều phối tập trung vào **Increment tích hợp** thay vì phần trăm task cục bộ.
- [ ] Sprint Planning xem rủi ro phụ thuộc và khả năng đạt Sprint Goal.
- [ ] Daily Scrum vẫn phục vụ Developers kiểm tra–thích ứng hướng Sprint Goal.
- [ ] Cơ chế liên nhóm giúp ra quyết định và tích hợp, không chỉ báo cáo trạng thái.
- [ ] Phụ thuộc thay đổi được thông báo sớm và điều chỉnh dự báo minh bạch.

### Khi vận hành và cải tiến

- [ ] Có runbook, monitoring, đầu mối on-call và chính sách rollback/khôi phục khi cần.
- [ ] Đã định nghĩa mốc Started/Finished và cách tính flow metrics.
- [ ] Theo dõi blocked time, dependency age, WIP, work item age, cycle time và chất lượng.
- [ ] Không dùng số dependency hoặc số commit để đánh giá cá nhân.
- [ ] Phụ thuộc lặp lại được xem xét nguyên nhân hệ thống, không chỉ xử lý từng ticket.
- [ ] Có thử nghiệm cải tiến nhỏ với baseline, metric chính và guardrails.
- [ ] Sau cải tiến, người dùng có nhận được giá trị sớm và đáng tin hơn không?
- [ ] Không chuyển hàng đợi hoặc rủi ro sang một nhóm khác để làm đẹp báo cáo.

Checklist phục vụ **đối thoại và kiểm chứng thực tế**, không phải một bộ thủ tục bổ sung cho mọi thay đổi. Nhóm chọn mức ghi chép và phối hợp tương xứng với rủi ro, quy mô và nghĩa vụ bắt buộc.

## 25. Tổng kết

**Nhận diện và giảm phụ thuộc giữa các nhóm** là một năng lực cốt lõi khi Agile mở rộng từ một nhóm liên chức năng tới nhiều nhóm cùng đóng góp vào giá trị sản phẩm.

Những điểm cần ghi nhớ:

1. **Bắt đầu từ luồng giá trị** và Increment có thể sử dụng, không chỉ từ sơ đồ phòng ban.
2. **Nhận diện rõ** bên cần, bên cung cấp, điều kiện kiểm chứng, tác động, thời điểm và chủ sở hữu.
3. **Phân biệt phụ thuộc cần giảm với ràng buộc phải giữ**: bảo mật, quyền, tính đúng đắn dữ liệu và nghĩa vụ tổ chức không phải thủ tục được bỏ để “nhanh hơn”.
4. **Ưu tiên loại bỏ hoặc giảm nguyên nhân** bằng lát cắt dọc, nhóm liên chức năng, hợp đồng ổn định, tự động hóa kiểm chứng, hạ tầng self-service và nâng năng lực.
5. **Điều phối những phụ thuộc còn lại** bằng owner, quyết định, thỏa thuận tương tác, mốc cần và escalation có phương án.
6. **Tích hợp sớm** với contract/integration tests, thay đổi tương thích và Definition of Done chung khi nhiều Scrum Team làm một sản phẩm.
7. **Đo toàn luồng** bằng blocked time, work item age, cycle time, chất lượng và kết quả người dùng; không tối ưu một nhóm bằng cách chuyển hàng đợi sang nhóm khác.
8. **Học từ phụ thuộc lặp lại** để điều chỉnh quy trình, ranh giới dịch vụ hoặc thiết kế nhóm, thay vì chỉ lập thêm lịch họp.

Trong **Scrum**, sự đồng bộ phải bảo vệ Product Goal và khả năng tạo Increment đạt DoD. Trong **Kanban**, phụ thuộc phải hiện trong workflow, WIP, thời gian chờ và những chính sách rõ ràng. Các thực hành **XP/CI** giảm độ trễ kỹ thuật; **Lean** giúp loại bỏ lãng phí, tối ưu cả hệ thống và tôn trọng con người.

Mục tiêu cuối không phải một hệ thống có **ít mũi tên trên sơ đồ** nhất, mà là một tổ chức có thể **phối hợp, tích hợp, giao phần mềm đáng tin cậy và nhận phản hồi với ít bất định và ít chờ đợi không cần thiết**.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Cross-team dependency** | Quan hệ một nhóm cần đầu ra, quyết định, tài nguyên hoặc điều kiện do bên khác ảnh hưởng/chi phối. |
| **Consumer / provider** | Bên sử dụng đầu ra hoặc hợp đồng / bên cung cấp nó. |
| **Blocker** | Điều kiện hiện đang ngăn công việc tiếp tục theo policy. |
| **Dependency risk** | Nguy cơ một phụ thuộc sẽ gây chặn hoặc làm lại trong tương lai. |
| **Handoff** | Lần chuyển giao công việc, thông tin, đầu ra hoặc quyền xử lý. |
| **Bottleneck** | Điểm giới hạn năng lực hoặc chính sách làm công việc tích tụ hàng đợi. |
| **Dependency mapping** | Trực quan hóa các ràng buộc và mối quan hệ cần đầu ra/điều kiện giữa hạng mục/nhóm. |
| **Dependency Structure Matrix (DSM)** | Ma trận mô tả những phụ thuộc giữa các phần tử với quy ước hàng/cột rõ ràng. |
| **Dependency register** | Bản ghi có thể hành động về phụ thuộc, owner, đầu ra, rủi ro, mốc và trạng thái. |
| **Vertical slice** | Phần công việc đi xuyên các tầng cần thiết để tạo hành vi có giá trị và kiểm chứng được. |
| **Cross-functional team** | Nhóm có những năng lực cần thiết để tự tạo phần lớn kết quả sản phẩm đã định. |
| **Coupling** | Mức độ các thành phần/nhóm phải thay đổi, hiểu hoặc triển khai cùng nhau. |
| **API / contract testing** | Giao diện dịch vụ / kiểm tra những kỳ vọng giao tiếp giữa consumer và provider. |
| **Consumer-driven contract** | Cách consumer thể hiện kỳ vọng và provider kiểm chứng tính tương thích với chúng. |
| **Expand–migrate–contract** | Thay hợp đồng/schema qua các bước tương thích, chuyển đổi và loại bỏ phần cũ. |
| **Feature flag** | Cơ chế điều khiển mức mở tính năng, không thay thế phân quyền. |
| **Branch by abstraction** | Đưa lớp trừu tượng chuyển tiếp để thay một triển khai lớn qua các bước nhỏ. |
| **Platform self-service** | Khả năng nhóm sản phẩm tự dùng dịch vụ nền tảng trong quyền/tiêu chuẩn có kiểm soát. |
| **Stream-aligned team** | Mô hình nhóm tập trung một luồng giá trị hoặc miền thay đổi sản phẩm. |
| **Enabling team** | Mô hình nhóm hỗ trợ nâng năng lực để nhóm khác bớt phụ thuộc lâu dài. |
| **Team Topologies** | Mô hình tham khảo thiết kế kiểu nhóm và cách tương tác để hỗ trợ flow. |
| **Conway's Law** | Quan sát về ảnh hưởng giữa cấu trúc giao tiếp tổ chức và cấu trúc hệ thống. |
| **Product Goal / Product Backlog / Product Owner** | Mục tiêu dài hạn của sản phẩm / danh sách có thứ tự công việc cần thiết / accountability tối đa hóa giá trị trong Scrum. |
| **Definition of Done (DoD)** | Cam kết chuẩn chất lượng của Increment trong Scrum. |
| **Increment** | Phần sản phẩm tăng thêm đã tích hợp, có thể sử dụng và đáp ứng DoD. |
| **Scrum of Scrums** | Kỹ thuật điều phối các nhóm theo nhu cầu, không phải sự kiện bắt buộc của Scrum Guide. |
| **Nexus** | Framework mở rộng Scrum hướng tới Increment tích hợp khi nhiều Scrum Team cùng một sản phẩm. |
| **Definition of Workflow (DoW)** | Cách nhóm Kanban xác định ranh giới, trạng thái và policy điều hành flow. |
| **WIP / work item age / cycle time / throughput** | Các chỉ số việc dở, tuổi việc dở, thời gian hoàn tất và lượng hoàn tất. |
| **Blocked time / dependency age** | Thời gian bị chặn / tuổi của phụ thuộc theo mốc đo được công bố. |
| **SLE** | Service Level Expectation: kỳ vọng có tính xác suất về thời gian hoàn tất theo dữ liệu workflow. |
| **Little's Law** | Quan hệ WIP–throughput–thời gian trung bình trong hệ thống thỏa các giả định áp dụng. |
| **Working agreement** | Thỏa thuận minh bạch cách cộng tác, chuyển giao, kiểm chứng và escalation. |
| **Escalation** | Đưa vấn đề tới chuyên môn hoặc thẩm quyền cần thiết để quyết định/hành động. |
| **ADR** | Architecture Decision Record: bản ghi ngắn một quyết định kiến trúc quan trọng và lý do. |
| **RACI / DACI** | Công cụ mô tả trách nhiệm hoặc quyền trong quyết định; không thay accountabilities chính thức của Scrum. |
