# Dọn execution khi kết thúc hoặc khi vượt giới hạn

Spring Web Flow quản lý hành trình web nhiều bước bằng flow execution. Một execution có thể đi qua nhiều view-state, action-state, transition và subflow trước khi hoàn tất. Trong lúc tạm dừng chờ người dùng, ứng dụng cần lưu trạng thái execution để request tiếp theo có thể tiếp tục đúng bước. Khi flow kết thúc hoặc khi người dùng mở quá nhiều hành trình cùng lúc, dữ liệu lưu trữ cần được dọn theo chính sách rõ ràng.

Việc dọn execution giúp tránh giữ trạng thái đã hoàn tất quá lâu, giới hạn dung lượng session hoặc kho lưu trữ, và kiểm soát số lượng snapshot dùng cho điều hướng quay lại. Cần phân biệt ba tình huống: execution gốc kết thúc, execution cũ bị loại khi vượt giới hạn và snapshot cũ bị loại trong một execution vẫn còn hoạt động. Mỗi tình huống có vòng đời và tác động khác nhau.

## 1. Flow execution được lưu để làm gì?

Khi người dùng gửi event từ một view-state, Spring Web Flow tiếp tục execution, thực hiện binding, validation, action và transition. Nếu flow tạm dừng tại một view-state khác, execution được lưu để request sau có thể khôi phục và tiếp tục. Repository chịu trách nhiệm lưu, tìm lại và loại bỏ execution theo key.

Trong một ứng dụng Spring MVC, luồng xử lý khái quát như sau:

~~~text
HTTP request
     |
     v
FlowHandlerMapping
     |
     v
FlowHandlerAdapter
     |
     v
FlowExecutor
     |
     v
FlowExecutionRepository
     |
     +---- tải execution đã lưu
     |
     v
Flow execution tiếp tục
     |
     +---- tạm dừng tại view-state
     |          |
     |          v
     |     lưu execution / snapshot
     |
     +---- kết thúc flow gốc
                |
                v
          loại execution đã kết thúc
~~~

**FlowExecutionRepository** là lớp lưu trữ mà executor dùng để quản lý execution. Với repository mặc định dựa trên HTTP session, trạng thái được gắn với phiên người dùng. Một repository khác có thể lưu snapshot vào database hoặc một kho lưu trữ phù hợp với kiến trúc triển khai.

Repository không chỉ lưu dữ liệu form. Nó lưu trạng thái cần thiết để tái tạo tiến trình flow, bao gồm flow session, state hiện tại, scope và thông tin snapshot. Vì vậy, một execution bị giữ lại sau khi không còn cần thiết sẽ chiếm tài nguyên nhiều hơn một biến đơn lẻ.

## 2. Phân biệt FlowExecution, FlowSession và snapshot

Ba khái niệm này có liên quan nhưng không thể dùng thay thế nhau:

| Thành phần | Ý nghĩa | Vòng đời |
|---|---|---|
| **FlowExecution** | Một lần thực thi của flow mà trình duyệt tiếp tục qua các request. | Từ lúc khởi chạy flow gốc đến khi flow gốc kết thúc hoặc execution bị loại bỏ. |
| **FlowSession** | Một phiên chạy của một flow trong execution; subflow có thể tạo session con bên trong session cha. | Có thể kết thúc khi subflow trả về, trong khi execution tổng thể vẫn tiếp tục. |
| **Execution snapshot** | Ảnh chụp trạng thái của execution tại một thời điểm tạm dừng. | Được giữ theo giới hạn snapshot để hỗ trợ tiếp tục hoặc điều hướng quay lại. |

Ví dụ, flow đặt chỗ gọi subflow thu thập địa chỉ. Khi subflow kết thúc, FlowSession của subflow đóng và flow cha tiếp tục. Đây không phải lúc để xóa toàn bộ FlowExecution vì người dùng vẫn còn ở giữa hành trình đặt chỗ.

Ngược lại, khi flow gốc đi đến end-state, toàn bộ hành trình hoàn tất. Executor có thể xử lý kết quả cuối cùng và repository loại execution đã kết thúc theo vòng đời của nó. Vì vậy, cần xác định rõ đang kết thúc subflow hay kết thúc flow gốc trước khi áp dụng chính sách dọn.

Snapshot cũng khác execution. Xóa một snapshot cũ chỉ làm mất một mốc trạng thái lịch sử; nó không nhất thiết kết thúc execution đang hoạt động. Đây là cơ chế quan trọng khi giới hạn số lần quay lại trong cùng một hành trình.

## 3. Dọn execution khi flow gốc kết thúc

Khi flow gốc đi đến end-state, execution không còn cần được tiếp tục bằng một request flow khác. Executor và repository quản lý vòng đời kết thúc này, bao gồm việc loại execution đã kết thúc khỏi kho lưu trữ theo hợp đồng của repository.

Một số nguyên tắc cần giữ:

- Để flow kết thúc qua end-state và để FlowExecutor quản lý vòng đời execution.
- Không tự xóa execution từ action nghiệp vụ khi flow vẫn cần xử lý kết quả hoặc còn transition tiếp theo.
- Nếu cần chuyển kết quả cho Spring MVC, khai báo output ở end-state và xử lý kết quả trong flow handler theo tích hợp tương ứng.
- Chỉ lưu dữ liệu nghiệp vụ cần tồn tại sau flow vào database hoặc kho nghiệp vụ riêng. Không dựa vào execution đã kết thúc làm nơi lưu hồ sơ lâu dài.
- Thiết kế action kết thúc an toàn khi được gọi lại, vì request có thể bị retry hoặc phản hồi có thể bị mất sau khi nghiệp vụ đã commit.

Ví dụ flow đơn giản:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">

    <view-state id="reviewBooking" view="booking/review">
        <transition on="confirm" to="saveBooking"/>
    </view-state>

    <action-state id="saveBooking">
        <evaluate expression="bookingService.confirm(booking)"/>
        <transition on="success" to="bookingConfirmed"/>
        <transition on="rejected" to="reviewBooking"/>
    </action-state>

    <end-state id="bookingConfirmed">
        <output name="bookingId" value="booking.id"/>
    </end-state>
</flow>
~~~

Khi flow đi đến **bookingConfirmed**, hành trình kết thúc và output **bookingId** có thể được tích hợp Spring MVC sử dụng. Nếu cần tra cứu đặt chỗ về sau, service phải lưu booking trong kho dữ liệu nghiệp vụ. Việc flow execution được dọn không được làm mất bản ghi booking đã commit.

Nếu flow kết thúc do hủy hoặc lỗi nghiệp vụ, hãy dùng end-state tương ứng để biểu diễn kết quả. Trước khi kết thúc, giải phóng những tài nguyên tạm thời mà nghiệp vụ đã giữ, chẳng hạn reservation có thời hạn hoặc lock do ứng dụng quản lý. Repository dọn execution không tự biết cách hoàn tác mọi tài nguyên bên ngoài flow.

## 4. Giới hạn số execution trong một conversation

Người dùng có thể mở nhiều flow execution trong cùng một conversation hoặc phiên trình duyệt, ví dụ mở nhiều tab đặt chỗ. Nếu giữ tất cả execution vô hạn, dữ liệu trong session hoặc repository có thể tăng liên tục.

Spring Web Flow cho phép giới hạn số execution được giữ trong một conversation bằng thuộc tính **max-executions** trên cấu hình flow executor. Khi vượt giới hạn, execution cũ nhất trong nhóm có thể bị loại theo chính sách repository mặc định để nhường chỗ cho execution mới.

Ví dụ cấu hình XML:

~~~xml
<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry"
                       max-executions="5"
                       max-execution-snapshots="15">
</webflow:flow-executor>
~~~

Trong ví dụ:

- **max-executions="5"** giới hạn số flow execution được giữ trong một conversation.
- **max-execution-snapshots="15"** giới hạn số snapshot được giữ cho mỗi execution.

Các giá trị trên chỉ là ví dụ. Hãy chọn giới hạn dựa trên kích thước dữ liệu flow, số tab người dùng thường mở, khả năng lưu trữ của session và nhu cầu điều hướng quay lại. Không nên coi giới hạn này là số execution tối đa trên toàn bộ máy chủ; nó được áp dụng theo conversation mà repository quản lý.

Khi execution vượt giới hạn bị loại, tab cũ có thể không còn tiếp tục được. Nếu người dùng quay lại tab đó, ứng dụng có thể báo execution không còn tồn tại hoặc yêu cầu bắt đầu lại hành trình. Đây là hành vi cần được dự tính trong trải nghiệm người dùng, đặc biệt với quy trình dài.

## 5. Giới hạn snapshot trong một execution

Trong quá trình chạy flow, repository có thể giữ các snapshot tại những thời điểm execution tạm dừng. Snapshot hỗ trợ tiếp tục flow bằng execution key và có thể hỗ trợ các hành vi quay lại theo cấu hình, nhưng mỗi snapshot đều tiêu tốn bộ nhớ hoặc dung lượng lưu trữ.

Thuộc tính **max-execution-snapshots** đặt giới hạn số snapshot được giữ cho một execution. Khi số snapshot vượt giới hạn, snapshot cũ nhất có thể bị loại. Execution hiện tại vẫn có thể tiếp tục với snapshot mới nhất còn hợp lệ.

Ví dụ, người dùng đi qua 20 lần tạm dừng trong một flow nhưng giới hạn là 15 snapshot. Repository có thể loại các snapshot cũ để giữ tập snapshot gần nhất. Điều này giới hạn khả năng quay lại rất sâu trong lịch sử của cùng flow.

| Giới hạn | Phạm vi | Khi vượt giới hạn |
|---|---|---|
| **max-executions** | Các execution trong một conversation | Execution cũ nhất có thể bị loại khỏi conversation. |
| **max-execution-snapshots** | Các snapshot của một execution | Snapshot cũ nhất có thể bị loại, execution vẫn hoạt động. |

Đừng đặt hai giới hạn bằng nhau một cách máy móc. Một người dùng có thể chỉ mở một execution nhưng đi qua rất nhiều bước; khi đó giới hạn snapshot ảnh hưởng nhiều hơn. Ngược lại, người dùng có thể mở nhiều flow ngắn ở nhiều tab; khi đó giới hạn execution trong conversation quan trọng hơn.

## 6. Chọn giới hạn theo dữ liệu và trải nghiệm

Giới hạn quá thấp có thể khiến người dùng mất một hành trình đang mở khi tạo flow mới hoặc không thể quay lại các bước trước. Giới hạn quá cao làm tăng dung lượng session, số snapshot và chi phí phục hồi.

Khi chọn giá trị, hãy xem xét:

- **Kích thước execution:** flow scope chứa object lớn, collection hoặc dữ liệu không cần thiết sẽ làm mỗi snapshot tốn nhiều tài nguyên.
- **Số tab thực tế:** người dùng có thường mở nhiều quy trình song song không?
- **Độ dài hành trình:** flow có nhiều view-state hoặc action-state tạm dừng không?
- **Nhu cầu quay lại:** người dùng có cần quay về nhiều bước cũ, hay chỉ cần tiếp tục từ bước gần nhất?
- **Tính chất nghiệp vụ:** một hành trình bị loại có thể bắt đầu lại an toàn không, hay cần khôi phục draft từ database?
- **Dung lượng session:** nếu session được lưu hoặc replicate giữa các node, snapshot lớn làm tăng chi phí truyền và phục hồi.

Nên lưu trong flow scope dữ liệu tối thiểu cần cho hành trình. Với dữ liệu lớn hoặc dữ liệu nghiệp vụ cần tồn tại lâu, hãy lưu trong database và chỉ giữ khóa tham chiếu trong flow. Cách này giảm kích thước execution và giúp giới hạn snapshot dễ dự đoán hơn.

## 7. Dọn execution khi session hết hạn

Với repository mặc định lưu trạng thái trong HTTP session, khi session bị invalidation hoặc hết hạn, dữ liệu session được servlet container thu hồi. Các execution gắn với session đó vì thế không còn được tiếp tục.

Tuy nhiên, không nên nhầm session timeout với chính sách hết hạn độc lập cho từng flow execution:

- Session timeout áp dụng cho toàn bộ session theo cấu hình web application hoặc servlet container.
- **max-executions** giới hạn số execution trong một conversation, không phải thời gian tồn tại của execution.
- **max-execution-snapshots** giới hạn số snapshot của mỗi execution, không phải thời gian tồn tại của snapshot.
- Repository tùy chỉnh lưu trong database hoặc cache cần tự xác định chính sách TTL và quy trình dọn bản ghi hết hạn.

Nếu ứng dụng dùng repository ngoài session, cần có cách nhận diện dữ liệu đã hết hạn và dọn an toàn. Có thể dùng TTL của kho lưu trữ hoặc một tác vụ định kỳ để xóa bản ghi hết hạn. Tác vụ đó cần phân biệt execution còn hoạt động với execution đã kết thúc hoặc đã quá hạn, đồng thời phối hợp với cơ chế khóa để không xóa execution đang được request khác tiếp tục.

Không dùng một câu lệnh xóa theo thời gian tạo đơn giản nếu nó có thể xóa execution đang hoạt động. Hãy có trường thời điểm cập nhật hoặc trạng thái vòng đời phù hợp, xác định thời hạn dựa trên chính sách sản phẩm và kiểm tra trạng thái trong transaction trước khi xóa.

## 8. Repository tùy chỉnh và trách nhiệm dọn

Một repository tùy chỉnh có thể lưu execution snapshot vào database, distributed cache hoặc hệ thống lưu trữ khác. Dù cách triển khai khác nhau, nó cần duy trì các trách nhiệm cơ bản:

1. Lưu execution đang tạm dừng cùng key có thể dùng để tiếp tục.
2. Tải đúng execution khi nhận key hợp lệ.
3. Cập nhật snapshot theo quy tắc đồng thời của repository.
4. Loại execution khi flow gốc kết thúc hoặc khi chính sách giới hạn yêu cầu.
5. Loại snapshot cũ khi vượt giới hạn snapshot.
6. Dọn dữ liệu hết hạn khi session hoặc TTL kết thúc.
7. Xử lý request đồng thời để một request không ghi đè hoặc xóa trạng thái mới hơn.

Các thao tác lưu, cập nhật và xóa nên có tính nhất quán. Nếu hai request cùng tiếp tục một execution, repository cần dùng cơ chế khóa hoặc kiểm soát phiên bản phù hợp để tránh cập nhật snapshot sai thứ tự. Nếu một request đang xử lý mà request khác xóa execution, kết quả phải được xác định rõ và không để lại dữ liệu mồ côi.

Không nên xóa trực tiếp bản ghi repository từ controller hoặc action nghiệp vụ bằng cách tự xây dựng key. FlowExecutor sở hữu vòng đời execution; việc xóa ngoài luồng điều khiển có thể khiến request tiếp theo không tìm thấy execution, hoặc làm mất trạng thái mà executor vẫn đang xử lý.

Nếu cần tùy chỉnh repository, hãy triển khai theo API của đúng phiên bản Spring Web Flow và giữ các hành vi parse key, lock, snapshot, lưu và remove nhất quán. Không giả định cấu trúc key hoặc schema lưu trữ nội bộ là ổn định giữa các phiên bản.

## 9. Xử lý khi người dùng quay lại execution đã bị dọn

Khi execution cũ hoặc snapshot cũ đã bị loại, trình duyệt có thể vẫn giữ URL hoặc execution key cũ. Request quay lại khi đó không còn tìm thấy trạng thái tương ứng.

Ứng dụng nên có cách xử lý rõ ràng:

- Thông báo hành trình đã hết hiệu lực hoặc không còn khả dụng.
- Cung cấp liên kết bắt đầu lại flow từ đầu.
- Nếu nghiệp vụ cho phép, tải draft đã lưu trong database và khởi tạo flow mới từ dữ liệu đó.
- Không tự tạo một execution mới rồi giả định nó có cùng trạng thái với tab cũ.
- Không tiết lộ key nội bộ, nội dung snapshot hoặc dữ liệu của execution khác trong thông báo lỗi.

Với flow có thao tác ghi, hãy bảo đảm việc bắt đầu lại không tạo giao dịch trùng. Dùng mã lệnh nghiệp vụ ổn định và cơ chế idempotency ở service khi cần. Việc execution bị dọn không chứng minh giao dịch trước đó đã rollback; có thể giao dịch đã commit trước khi flow hoàn tất hoặc trước khi response bị mất.

## 10. Theo dõi và vận hành chính sách dọn

Để biết giới hạn có phù hợp không, hãy theo dõi các chỉ số vận hành:

- Số execution đang được giữ theo conversation hoặc theo người dùng ở mức tổng hợp phù hợp.
- Số snapshot trung bình và kích thước snapshot.
- Số lần execution bị loại do vượt **max-executions**.
- Số snapshot bị loại do vượt **max-execution-snapshots**.
- Số request không tìm thấy execution hoặc snapshot cũ.
- Dung lượng session, cache hoặc bảng lưu trữ execution.
- Số lỗi khi lưu, phục hồi hoặc dọn execution.

Có thể dùng FlowExecutionListener để ghi nhận sự kiện vòng đời như bắt đầu, kết thúc session flow hoặc lỗi thực thi, tùy callback có trong phiên bản thư viện. Listener phù hợp cho log, metric và audit. Không nên dùng listener như nơi thay thế repository để tự xóa dữ liệu lưu trữ nếu framework đã quản lý vòng đời đó.

Log nên có flow id, execution key ở dạng đã được kiểm soát, state hoặc kết quả và thời điểm xử lý. Không ghi toàn bộ flow scope hay dữ liệu cá nhân vào log. Khi đo lường việc dọn do vượt giới hạn, nên phân biệt execution bị loại với snapshot bị loại để tránh hiểu nhầm rằng người dùng đã mất toàn bộ hành trình.

## 11. Kiểm thử chính sách dọn execution

Kiểm thử nên bao gồm cả hành vi của executor và repository, không chỉ kiểm tra một giá trị cấu hình:

1. **Flow kết thúc bình thường.** Xác nhận flow gốc đi đến end-state, output cần thiết được xử lý và execution không còn được tiếp tục như một flow đang hoạt động.
2. **Subflow kết thúc.** Xác nhận session con đóng nhưng flow cha vẫn tiếp tục và execution tổng thể chưa bị xóa.
3. **Vượt max-executions.** Mở nhiều execution trong cùng conversation vượt giới hạn; xác nhận execution cũ bị loại theo chính sách và execution mới có thể tiếp tục.
4. **Vượt max-execution-snapshots.** Tạo nhiều snapshot trong một execution; xác nhận snapshot cũ bị loại nhưng execution mới nhất vẫn hoạt động.
5. **Dùng lại key đã hết hiệu lực.** Xác nhận request nhận phản hồi phù hợp và ứng dụng đưa người dùng đến hành động bắt đầu lại.
6. **Session hết hạn.** Xác nhận execution gắn với session không còn được phục hồi sau khi session invalidation.
7. **Repository có TTL.** Xác nhận tác vụ dọn chỉ xóa execution đã hết hạn và giữ execution đang hoạt động.
8. **Request đồng thời.** Giả lập một request tiếp tục flow trong lúc một tiến trình dọn chạy; xác nhận không xóa nhầm execution đang được sử dụng.
9. **Lỗi sau khi nghiệp vụ commit.** Giả lập response bị mất sau khi service ghi dữ liệu; xác nhận việc flow bị dọn không tạo giao dịch trùng khi người dùng bắt đầu lại.
10. **Giám sát.** Xác nhận log và metric phân biệt số execution bị loại với số snapshot bị loại.

Ở cấp tích hợp, kiểm tra repository sau từng tình huống bằng API công khai hoặc cơ chế kiểm thử được cung cấp. Tránh phụ thuộc vào cấu trúc nội bộ của session hoặc key encoding nếu không phải một phần hợp đồng API.

## 12. Quy trình chọn và triển khai chính sách dọn

Khi cấu hình lưu trữ execution cho ứng dụng, hãy làm theo trình tự:

1. Xác định repository đang dùng và phạm vi conversation mà repository quản lý.
2. Phân biệt flow gốc, subflow session và snapshot để xác định dữ liệu nào cần được giữ.
3. Đặt **max-executions** dựa trên số hành trình song song người dùng cần mở.
4. Đặt **max-execution-snapshots** dựa trên nhu cầu quay lại và kích thước trạng thái.
5. Giảm dữ liệu trong flow scope; lưu dữ liệu nghiệp vụ dài hạn ở kho riêng.
6. Xác nhận flow gốc kết thúc qua end-state và executor xử lý vòng đời execution.
7. Nếu dùng repository ngoài session, bổ sung TTL hoặc tác vụ dọn có kiểm soát đồng thời.
8. Thiết kế thông báo và cách khởi động lại khi execution key đã hết hiệu lực.
9. Theo dõi dung lượng, số lần eviction và lỗi phục hồi để điều chỉnh giới hạn.
10. Kiểm thử kết thúc flow, subflow, vượt giới hạn, session hết hạn và request đồng thời.

## 13. Ghi nhớ

FlowExecutor và FlowExecutionRepository phối hợp quản lý vòng đời execution. Khi flow gốc kết thúc, execution được loại theo vòng đời của repository. **max-executions** giới hạn số execution trong một conversation; **max-execution-snapshots** giới hạn số snapshot của mỗi execution. Khi vượt giới hạn, execution cũ hoặc snapshot cũ có thể bị loại, nhưng hai trường hợp có tác động khác nhau.

Subflow kết thúc không có nghĩa flow execution tổng thể kết thúc. Session timeout cũng khác giới hạn execution và giới hạn snapshot. Với repository tùy chỉnh, cần có TTL hoặc tác vụ dọn an toàn, kiểm soát request đồng thời và trải nghiệm khởi động lại khi key hết hiệu lực. Theo dõi dung lượng và kiểm thử các trường hợp vượt giới hạn sẽ giúp lưu trữ execution ổn định trong ứng dụng Spring Web Flow nhiều bước.
