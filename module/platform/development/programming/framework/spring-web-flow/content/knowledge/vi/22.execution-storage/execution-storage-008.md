# Giới hạn lịch sử bằng max-execution-snapshots

Trong chương **Lưu trữ execution**, bài này giải thích cách giới hạn lịch sử snapshot của một flow execution bằng thuộc tính **max-execution-snapshots** trong Spring Web Flow. Module **SPRING_WEB_FLOW** dùng state, event, transition và subflow để mô hình hóa hành trình nhiều bước; repository lưu và khôi phục execution giữa các request. Snapshot giúp framework khôi phục một trạng thái đã tạm dừng, hỗ trợ điều hướng lịch sử và xử lý request tiếp theo theo đúng execution. Tuy nhiên, giữ quá nhiều snapshot làm tăng dung lượng lưu trữ và lượng dữ liệu cần quản lý.

**max-execution-snapshots** đặt giới hạn số snapshot được giữ cho một flow execution. Khi lịch sử vượt giới hạn, các snapshot cũ nhất có thể bị loại khỏi nhóm snapshot của execution theo chính sách repository. Vì vậy, cấu hình này là một quyết định cân bằng giữa khả năng quay lại trạng thái cũ và chi phí lưu trữ.

## Snapshot là gì trong vòng đời execution?

Một flow execution là một lần chạy cụ thể của flow definition. Trong quá trình đó, người dùng có thể đi qua nhiều view-state, phát event và chuyển state nhiều lần. Khi flow tạm dừng giữa các request, repository có thể lưu snapshot để lần request sau tìm lại và tiếp tục execution. Snapshot ghi lại trạng thái cần thiết để khôi phục flow tại một thời điểm, theo cơ chế snapshot và repository đang cấu hình.

Hãy hình dung quy trình đặt hàng:

1. Người dùng mở flow và nhập thông tin giao hàng.
2. Flow chuyển tới màn hình xem lại.
3. Người dùng quay lại sửa địa chỉ.
4. Flow chuyển tiếp tới lựa chọn thanh toán.
5. Người dùng quay lại màn hình xem lại để điều chỉnh lựa chọn.

Các snapshot cho phép repository khôi phục một trạng thái trước đó khi request mang execution key phù hợp. Nhờ vậy, nút Back của trình duyệt hoặc hành động quay lại được flow hỗ trợ có thể khôi phục ngữ cảnh tương ứng, miễn là snapshot đó vẫn còn và request vẫn hợp lệ.

~~~mermaid
flowchart TD
    A["Flow execution bắt đầu"] --> B["State: shipping"]
    B --> C["Flow tạm dừng / snapshot được lưu"]
    C --> D["State: review"]
    D --> E["Snapshot tiếp theo"]
    E --> F["State: payment"]
    F --> G["Snapshot tiếp theo"]
    G --> H["Người dùng quay lại"]
    H --> I{"Snapshot cần khôi phục còn được giữ?"}
    I -->|"Có"| J["Repository khôi phục execution"]
    I -->|"Không"| K["Không thể khôi phục snapshot cũ"]
    J --> L["Tiếp tục flow từ trạng thái tương ứng"]
~~~

Snapshot là dữ liệu trạng thái phía server, không phải ảnh chụp màn hình trình duyệt. Trình duyệt có thể giữ nội dung trang trong cache, nhưng việc hiển thị lại trang cũ không chứng minh server còn snapshot để xử lý một request tiếp theo. Khi điều hướng, flow execution key và thông tin snapshot do Web Flow quản lý mới là căn cứ để repository tìm trạng thái cần phục hồi.

Thời điểm tạo snapshot phụ thuộc vòng đời pause/resume và cấu hình repository. Không nên giả định mỗi lần người dùng nhấn nút hoặc mỗi transition đều chắc chắn tạo đúng một snapshot. Khi đo đạc hoặc kiểm thử, hãy xác nhận hành vi của phiên bản và repository thực tế.

## max-execution-snapshots kiểm soát điều gì?

Thuộc tính **max-execution-snapshots** giới hạn số snapshot được giữ trong lịch sử của một flow execution. Nó giúp ngăn lịch sử của một hành trình phát triển không giới hạn khi người dùng đi qua nhiều bước hoặc điều hướng qua lại nhiều lần.

Ví dụ, nếu giới hạn là 5, repository chỉ giữ tối đa 5 snapshot cho execution theo chính sách của nó. Khi có snapshot mới vượt giới hạn, snapshot cũ nhất trong lịch sử có thể bị loại bỏ. Những snapshot gần đây vẫn có thể được khôi phục, còn một URL hoặc execution key trỏ tới snapshot đã bị loại bỏ có thể không còn dùng được.

| Khái niệm | Ý nghĩa | Phạm vi |
|---|---|---|
| Flow definition | Bản thiết kế các state, event và transition | Được đăng ký trong ứng dụng |
| Flow execution | Một lần chạy cụ thể của flow | Một hành trình đang hoặc đã chạy |
| Snapshot | Trạng thái có thể dùng để khôi phục execution tại một thời điểm | Một mốc trong lịch sử của execution |
| max-execution-snapshots | Số snapshot tối đa được giữ cho execution | Giới hạn lịch sử của từng execution |
| Số execution đồng thời | Số hành trình riêng biệt đang được quản lý | Phạm vi repository/session và cấu hình liên quan |

Cần phân biệt giới hạn snapshot với giới hạn số execution. Một người dùng có thể mở nhiều flow execution khác nhau; mỗi execution lại có lịch sử snapshot riêng. **max-execution-snapshots** không phải là số flow mà người dùng được phép mở, cũng không phải số request tối đa trong session.

## Cấu hình giới hạn snapshot

Trong cấu hình XML của Spring Web Flow, có thể khai báo giới hạn trong phần flow execution repository của flow executor. Ví dụ dưới đây đặt giới hạn là 5 snapshot cho mỗi execution:

~~~xml
<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry">
    <webflow:flow-execution-repository
            max-execution-snapshots="5" />
</webflow:flow-executor>
~~~

Prefix namespace trong ví dụ là **webflow**; ứng dụng cần khai báo namespace và schema Spring Web Flow tương ứng với phiên bản đang sử dụng. Nếu dự án dùng prefix khác, tên prefix có thể khác nhưng phần tử cấu hình vẫn phải thuộc namespace Web Flow.

Chọn con số 5 chỉ là ví dụ. Giá trị phù hợp phụ thuộc vào độ dài hành trình, mức độ cần hỗ trợ quay lại, kích thước snapshot, số người dùng đồng thời và cơ chế lưu trữ. Không nên chọn một con số chỉ vì nó xuất hiện trong ví dụ tài liệu.

Nếu cấu hình repository bằng Java hoặc tự cung cấp repository bean, hãy dùng API/builder và thuộc tính tương ứng của đúng phiên bản Spring Web Flow. Không trộn cấu hình XML của phiên bản này với API của phiên bản khác. Sau khi cấu hình, cần xác nhận repository thực tế nhận được giới hạn mong muốn thay vì chỉ kiểm tra file cấu hình có chứa thuộc tính.

## Điều gì xảy ra khi vượt giới hạn?

Giả sử giới hạn là 3 và execution đã có các snapshot theo thứ tự thời gian:

| Thời điểm | Hành động | Lịch sử được giữ sau hành động |
|---|---|---|
| T1 | Lưu snapshot đầu tiên | S1 |
| T2 | Lưu snapshot thứ hai | S1, S2 |
| T3 | Lưu snapshot thứ ba | S1, S2, S3 |
| T4 | Lưu snapshot thứ tư | S2, S3, S4 |
| T5 | Lưu snapshot thứ năm | S3, S4, S5 |

Khi snapshot thứ tư được lưu, snapshot cũ nhất S1 không còn trong nhóm lịch sử nếu repository áp dụng chính sách loại bỏ snapshot cũ nhất để tuân thủ giới hạn. Snapshot S2 và S3 vẫn được giữ cùng snapshot mới S4. Quy tắc chi tiết về thời điểm snapshot được tạo, việc giữ snapshot hiện tại và xử lý tham chiếu cũ cần được xác nhận theo implementation và phiên bản đang chạy.

Hệ quả đối với người dùng là họ có thể quay lại một số bước gần đây, nhưng không thể giả định mọi trạng thái từ đầu hành trình đều còn khả năng phục hồi. Nếu người dùng dùng một tab rất cũ hoặc gửi lại URL tham chiếu snapshot đã bị loại bỏ, repository có thể không tìm thấy snapshot tương ứng. Ứng dụng cần xử lý trường hợp này như một execution/snapshot không còn hợp lệ: thông báo rõ ràng, đưa người dùng tới điểm bắt đầu phù hợp hoặc hướng dẫn khởi tạo một hành trình mới.

Không nên tự khôi phục bằng cách tạo một flow execution mới rồi gắn nó vào URL cũ. Execution mới không có cùng lịch sử, dữ liệu hoặc ngữ cảnh nghiệp vụ với execution đã hết snapshot.

## Chọn giới hạn dựa trên nhu cầu điều hướng

Giới hạn nhỏ làm giảm lịch sử có thể quay lại. Giới hạn lớn giữ được nhiều mốc hơn nhưng làm tăng dung lượng lưu trữ và chi phí serialize/deserialize nếu repository dùng serialization.

| Loại flow | Đặc điểm | Cách chọn giới hạn |
|---|---|---|
| Biểu mẫu ngắn 2–3 bước | Ít state, ít nhu cầu quay lại xa | Có thể dùng giới hạn nhỏ sau khi kiểm thử |
| Quy trình đăng ký nhiều bước | Người dùng có thể sửa thông tin ở các bước trước | Giữ đủ lịch sử cho các bước quay lại thường gặp |
| Quy trình đặt hàng | Giá, tồn kho và báo giá có thể thay đổi theo thời gian | Giữ lịch sử vừa đủ; vẫn xác minh dữ liệu nghiệp vụ mới nhất |
| Quy trình phê duyệt dài | Nhiều state và hành động có tác động nghiệp vụ | Cân nhắc kỹ snapshot, quyền truy cập, timeout và trạng thái nghiệp vụ |
| Flow chứa dữ liệu lớn | Snapshot có object graph lớn hoặc collection nhiều phần tử | Ưu tiên giảm dữ liệu trong snapshot và đo chi phí trước khi tăng giới hạn |

Không phải lúc nào tăng số snapshot cũng là cách tốt nhất để hỗ trợ người dùng quay lại. Nếu người dùng cần giữ một bản nháp lâu dài, hãy lưu bản nháp vào kho dữ liệu nghiệp vụ có quyền sở hữu và thời hạn rõ ràng. Snapshot phục vụ khôi phục execution; nó không phải cơ chế lưu trữ hồ sơ lâu dài hoặc thay thế lịch sử nghiệp vụ.

## Ảnh hưởng tới bộ nhớ và lưu trữ

Một cách ước lượng sơ bộ là xem xét ba yếu tố:

- Số flow execution đang được quản lý đồng thời.
- Số snapshot trung bình được giữ cho mỗi execution, bị chặn bởi giới hạn cấu hình.
- Kích thước trung bình của một snapshot.

Có thể mô tả tải lưu trữ gần đúng như sau:

\[
\text{Dung lượng snapshot} \approx
\text{số execution} \times
\text{số snapshot mỗi execution} \times
\text{kích thước snapshot trung bình}
\]

Đây chỉ là mô hình ước lượng, không phải công thức đo chính xác. Repository có thể dùng tham chiếu, nén, cấu trúc lưu trữ riêng hoặc overhead khác. Nếu snapshot nằm trong HTTP session, kích thước session và cơ chế passivation/replication cũng có thể bị ảnh hưởng. Nếu repository lưu ngoài session, cần đo dung lượng và độ trễ của kho lưu trữ đó.

Một số cách giảm chi phí:

- Chỉ đưa dữ liệu cần thiết để khôi phục flow vào scope.
- Tránh giữ entity graph lớn, file, stream, connection hoặc dữ liệu dẫn xuất có thể tính lại.
- Lưu ID và DTO nhỏ thay vì toàn bộ đối tượng nghiệp vụ.
- Chọn scope đúng vòng đời, không giữ dữ liệu tạm trong conversation scope nếu không cần chia sẻ lâu.
- Đo kích thước snapshot và số execution thực tế trong tải thử.
- Điều chỉnh giới hạn theo hành vi quay lại quan sát được, thay vì tăng tùy ý.

Giới hạn snapshot giúp khống chế số mốc lịch sử, nhưng không sửa được một snapshot riêng lẻ quá lớn. Nếu mỗi snapshot giữ một object graph nặng, ngay cả giới hạn thấp cũng có thể tiêu tốn nhiều tài nguyên.

## Liên hệ với browser back và nhiều tab

Người dùng có thể nhấn nút Back của trình duyệt, mở nhiều tab hoặc gửi lại một form cũ. Các hành động đó có thể làm request mang execution key hoặc snapshot reference đã cũ. Khi lịch sử bị giới hạn, một tab lâu không hoạt động có thể trỏ tới snapshot đã bị loại bỏ trong khi tab mới hơn vẫn hoạt động.

Hãy phân biệt:

- **Back trong flow:** một event được định nghĩa như **backToShipping** có thể chuyển flow tới state trước theo quy tắc nghiệp vụ hiện tại.
- **Browser Back:** trình duyệt quay lại URL hoặc nội dung đã lưu; request tiếp theo có thể tham chiếu snapshot cũ.
- **Mở tab mới:** có thể tạo flow execution mới hoặc tiếp tục một execution hiện có tùy URL được mở.
- **Gửi lại form cũ:** có thể gửi event hoặc dữ liệu thuộc trạng thái không còn hợp lệ.

Với thao tác quan trọng như xác nhận đơn hoặc thanh toán, không dựa vào lịch sử snapshot để bảo vệ nghiệp vụ. Service cần xác minh trạng thái hiện tại, quyền sở hữu và tính hợp lệ của thao tác; các hành động có thể bị gửi lặp cần cơ chế idempotency phù hợp.

## Kiểm thử giới hạn max-execution-snapshots

Cần kiểm thử cả hành vi giữ snapshot và hành vi khi lịch sử vượt giới hạn. Một kịch bản kiểm thử tích hợp có thể thực hiện như sau:

1. Cấu hình repository với một giới hạn nhỏ, ví dụ 3.
2. Khởi chạy flow và đi qua đủ state để tạo nhiều snapshot theo vòng đời thực tế.
3. Ghi nhận các execution key hoặc URL tương ứng với các snapshot có thể kiểm tra.
4. Tiếp tục tạo snapshot vượt quá giới hạn.
5. Thử khôi phục một snapshot còn nằm trong lịch sử và xác nhận state cùng dữ liệu được phục hồi đúng.
6. Thử truy cập snapshot cũ đã bị loại khỏi lịch sử và xác nhận ứng dụng xử lý trạng thái không còn hợp lệ một cách có kiểm soát.
7. Kiểm tra một flow execution khác để bảo đảm giới hạn lịch sử của execution này không vô tình làm lẫn dữ liệu của execution kia.
8. Lặp lại với dữ liệu snapshot lớn và nhiều execution đồng thời để quan sát bộ nhớ, session size hoặc kho lưu trữ.

Khi kiểm thử, không nên chỉ đếm số lần nhấn nút. Một số request có thể không tạo snapshot mới, tùy điểm pause/resume và cấu hình. Hãy xác định các snapshot thực sự được repository tạo ra và kiểm tra giới hạn trên lịch sử đó.

### Ma trận kiểm thử gợi ý

| Tình huống | Kết quả mong đợi |
|---|---|
| Số snapshot chưa đạt giới hạn | Các snapshot được tạo vẫn có thể khôi phục theo key hợp lệ |
| Tạo thêm snapshot vượt giới hạn | Số snapshot được giữ không vượt quá giới hạn cấu hình |
| Truy cập snapshot cũ đã bị loại | Request được xử lý như snapshot/execution không còn hợp lệ |
| Tiếp tục snapshot mới nhất | Flow phục hồi đúng state và dữ liệu |
| Hai execution độc lập | Lịch sử của từng execution được quản lý riêng |
| Dữ liệu snapshot lớn | Tải lưu trữ được đo và nằm trong ngân sách vận hành |
| Người dùng mở tab cũ | Ứng dụng phản hồi an toàn khi snapshot tham chiếu không còn |

## Xử lý snapshot không còn tồn tại

Khi snapshot cũ bị loại bỏ, request có thể thất bại vì repository không thể khôi phục trạng thái được tham chiếu. Tùy cấu hình, lỗi có thể được biểu diễn qua exception liên quan đến flow execution hoặc snapshot không tìm thấy/hết hiệu lực. Không nên bắt một exception chung rồi âm thầm tạo execution mới, vì điều đó có thể làm người dùng tưởng rằng dữ liệu cũ đã được giữ.

Một cách xử lý phù hợp là:

1. Ghi log mã flow, execution key ở dạng phù hợp với chính sách bảo mật và loại lỗi; tránh ghi dữ liệu nhạy cảm của form.
2. Xác định request có trỏ tới snapshot đã hết hạn, execution đã kết thúc hay execution không tồn tại.
3. Hiển thị thông báo giải thích rằng phiên làm việc cũ không còn khả dụng.
4. Cung cấp đường dẫn để người dùng bắt đầu lại hoặc khôi phục bản nháp nghiệp vụ nếu ứng dụng có lưu riêng.
5. Với thao tác ghi dữ liệu, xác minh trạng thái nghiệp vụ để tránh xử lý trùng hoặc ghi đè dữ liệu mới hơn.

Nếu ứng dụng có cơ chế lưu draft bền vững, có thể dùng ID draft để khởi tạo một flow execution mới sau khi xác minh quyền truy cập. Đây là một hành trình mới dựa trên dữ liệu draft, không phải khôi phục snapshot đã bị loại.

## Các lỗi cấu hình và vận hành thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Người dùng không quay lại được bước quá cũ | Snapshot đã bị loại do vượt giới hạn | Kiểm tra giới hạn, số snapshot thực tế và snapshot reference |
| Dung lượng session tăng nhanh | Giới hạn quá cao hoặc mỗi snapshot chứa nhiều dữ liệu | Đo kích thước snapshot, giảm object graph và điều chỉnh giới hạn |
| Cấu hình không có tác dụng | Thuộc tính đặt sai phần tử, namespace hoặc executor đang dùng repository khác | Kiểm tra schema/version và bean repository thực tế |
| Lỗi khi mở tab cũ | URL tham chiếu snapshot không còn tồn tại | Kiểm tra exception repository và xử lý execution hết hạn |
| Flow mới bị ảnh hưởng bởi flow khác | Nhầm giới hạn snapshot với giới hạn execution hoặc dùng storage key không tách biệt | Kiểm tra phạm vi repository và định danh execution |
| Snapshot khôi phục nhưng dữ liệu nghiệp vụ cũ | Snapshot chỉ lưu trạng thái tại thời điểm trước | Nạp lại và xác minh dữ liệu có thẩm quyền trước thao tác cuối |

Đặc biệt, không nên tăng giới hạn để che lỗi snapshot quá lớn hoặc rò rỉ dữ liệu trong scope. Trước tiên hãy kiểm tra dữ liệu nào được giữ trong execution, snapshot được tạo ở thời điểm nào và repository nào đang quản lý chúng.

## Checklist chọn giới hạn

Trước khi triển khai cấu hình **max-execution-snapshots**, hãy rà soát:

- [ ] Đã xác định repository thực tế được flow executor sử dụng.
- [ ] Đã xác nhận thuộc tính cấu hình đúng với phiên bản Spring Web Flow của dự án.
- [ ] Đã xác định số bước người dùng thường cần quay lại.
- [ ] Đã đo kích thước snapshot và số execution đồng thời.
- [ ] Đã chọn giới hạn dựa trên nhu cầu điều hướng và ngân sách lưu trữ.
- [ ] Đã kiểm thử snapshot còn hạn và snapshot cũ bị loại.
- [ ] Đã có cách xử lý URL/tab tham chiếu snapshot không còn tồn tại.
- [ ] Đã phân biệt snapshot với draft nghiệp vụ bền vững.
- [ ] Đã kiểm tra nhiều tab, request gửi lại và thao tác nghiệp vụ có thể lặp.
- [ ] Đã theo dõi session size, bộ nhớ hoặc kho lưu trữ sau triển khai.

## Ghi nhớ

- **max-execution-snapshots** giới hạn số snapshot lịch sử được giữ cho một flow execution.
- Khi vượt giới hạn, snapshot cũ có thể bị loại bỏ; request trỏ tới snapshot đó không còn khôi phục được trạng thái tương ứng.
- Giới hạn snapshot khác với giới hạn số execution đồng thời và khác với lưu trữ draft nghiệp vụ.
- Chọn giá trị dựa trên nhu cầu quay lại, kích thước snapshot, số người dùng đồng thời và cơ chế repository.
- Kiểm thử cả snapshot còn được giữ, snapshot bị loại, nhiều execution và request từ tab cũ.
- Xác minh lại trạng thái nghiệp vụ ở server trước các thao tác quan trọng; snapshot không thay thế dữ liệu có thẩm quyền.

