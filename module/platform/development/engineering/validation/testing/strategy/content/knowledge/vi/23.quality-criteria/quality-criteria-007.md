# Tiêu chí chất lượng: Phân biệt tiêu chí chưa đạt với dữ liệu đánh giá chưa có

## 1. Vì sao cần phân biệt hai trạng thái này?

Khi đánh giá chất lượng sản phẩm, nhóm thường đối chiếu kết quả kiểm thử, số liệu vận hành hoặc bằng chứng nghiệm thu với các tiêu chí đã thống nhất. Một tiêu chí có thể đạt, không đạt hoặc chưa thể kết luận vì dữ liệu đánh giá chưa có hay chưa đủ. Nếu gộp hai trường hợp cuối thành một trạng thái, báo cáo sẽ dễ gây hiểu nhầm và dẫn tới quyết định sai.

**Tiêu chí chưa đạt** nghĩa là đã có bằng chứng hợp lệ, phù hợp với phạm vi đánh giá và bằng chứng đó cho thấy kết quả vi phạm ngưỡng hoặc điều kiện đã định nghĩa. **Dữ liệu đánh giá chưa có** nghĩa là chưa có bằng chứng đủ tin cậy để kết luận tiêu chí đạt hay không đạt. Đây là khoảng trống về khả năng đánh giá, không phải bằng chứng sản phẩm đã vi phạm tiêu chí.

Ví dụ, tiêu chí hiệu năng yêu cầu p95 không vượt quá 500 ms:

- Một lần đo hợp lệ, đủ mẫu và đại diện cho workload cho kết quả p95 là 720 ms: tiêu chí chưa đạt.
- Dashboard không thu thập được latency trong đợt chạy: chưa có dữ liệu đánh giá.
- Chỉ có ba request trong khi kế hoạch yêu cầu một workload đại diện: dữ liệu chưa đủ để kết luận.
- Số liệu cũ từ phiên bản trước không thể đại diện cho bản đang đánh giá: dữ liệu không còn phù hợp.

Trong **VALIDATION_TESTING_STRATEGY**, phân biệt chính xác hai trạng thái giúp nhóm không tuyên bố đạt khi thiếu bằng chứng, không gán lỗi sản phẩm khi phép đo không hợp lệ và biết phải xử lý khoảng trống nào trước khi đưa ra quyết định chất lượng.

## 2. Định nghĩa và ranh giới của trạng thái đánh giá

### 2.1. Tiêu chí chưa đạt

Một tiêu chí được đánh dấu chưa đạt khi:

- Tiêu chí và ngưỡng được xác định trước hoặc đã được phê duyệt.
- Bằng chứng đến từ nguồn phù hợp và đúng phiên bản/phạm vi.
- Phương pháp thu thập và tính toán hợp lệ.
- Dữ liệu đủ về số lượng, độ bao phủ và tính đại diện theo kế hoạch.
- Kết quả quan sát vi phạm điều kiện đạt.

Ví dụ: yêu cầu không có lỗi nghiêm trọng còn mở tại thời điểm phát hành. Danh sách defect được đồng bộ đầy đủ, có trạng thái và mức độ rõ ràng; vẫn còn một defect Critical chưa được xử lý. Đây là tiêu chí chưa đạt.

### 2.2. Chưa có dữ liệu đánh giá

Trạng thái này áp dụng khi nhóm chưa thể đưa ra kết luận vì thiếu một phần hoặc toàn bộ bằng chứng cần thiết, chẳng hạn:

- Chưa chạy hoạt động đánh giá.
- Hệ thống đo lường hoặc công cụ thu thập bị lỗi.
- Dữ liệu không được lưu hoặc không truy cập được.
- Thiếu mẫu, thiếu trường hợp hoặc thiếu khoảng thời gian quan sát.
- Không xác định được dữ liệu thuộc phiên bản hoặc môi trường nào.
- Nguồn dữ liệu không đáng tin cậy hoặc phương pháp đo chưa được xác nhận.

Không có dữ liệu không chứng minh sản phẩm tốt hay xấu. Nó cho biết quyết định về tiêu chí hiện chưa có đủ căn cứ.

### 2.3. Các trạng thái nên được tách riêng

Một hệ thống đánh giá rõ ràng có thể sử dụng các trạng thái sau:

| Trạng thái | Ý nghĩa | Có thể kết luận về tiêu chí? |
| --- | --- | --- |
| Đạt (Met) | Bằng chứng hợp lệ cho thấy điều kiện đạt được đáp ứng | Có |
| Chưa đạt (Not met) | Bằng chứng hợp lệ cho thấy điều kiện đạt bị vi phạm | Có |
| Chưa đánh giá (Not assessed) | Chưa thực hiện hoặc chưa thu được dữ liệu cần thiết | Không |
| Chưa đủ bằng chứng (Insufficient evidence) | Có dữ liệu nhưng thiếu mẫu, phạm vi hoặc chất lượng để kết luận | Không |
| Bị chặn (Blocked) | Không thể đánh giá do phụ thuộc, quyền hoặc môi trường chưa sẵn sàng | Không |
| Không áp dụng (Not applicable) | Tiêu chí không thuộc phạm vi đã xác định và có lý do được chấp thuận | Không cần áp dụng |
| Dữ liệu hết hạn (Stale) | Có dữ liệu nhưng không còn đại diện cho phiên bản hoặc thời điểm cần đánh giá | Không |

Có thể gộp một số trạng thái trong công cụ quản lý nếu quy trình cho phép, nhưng báo cáo vẫn phải phân biệt nguyên nhân. Đặc biệt, không chuyển tự động Not assessed, Insufficient evidence hoặc Blocked thành Met.

### 2.4. Tiêu chí chưa đạt khác với hoạt động đánh giá thất bại

Một lần chạy kiểm thử có thể thất bại do test harness, môi trường hoặc dữ liệu chuẩn bị sai. Điều đó không tự động chứng minh tiêu chí chất lượng sản phẩm chưa đạt.

Hãy phân biệt:

- **Test failed:** một test case không đạt assertion.
- **Evaluation failed:** hoạt động đánh giá không hoàn tất đúng phương pháp hoặc không tạo được bằng chứng hợp lệ.
- **Criterion not met:** bằng chứng hợp lệ cho thấy sản phẩm vi phạm tiêu chí.

Nếu test fail vì API trả kết quả nghiệp vụ sai trong môi trường sẵn sàng, đó có thể là bằng chứng tiêu chí chưa đạt. Nếu test fail vì database không khởi động, đây có thể là lỗi môi trường và tiêu chí chức năng vẫn chưa được đánh giá.

## 3. Xác định tiêu chí trước khi thu thập dữ liệu

### 3.1. Tiêu chí cần có điều kiện đạt rõ ràng

Một tiêu chí có thể được diễn đạt theo cấu trúc:

- **Thuộc tính:** điều gì cần được đánh giá?
- **Phạm vi:** thành phần, hành trình, phiên bản hoặc nhóm người dùng nào?
- **Phương pháp:** đo hoặc xác nhận bằng cách nào?
- **Ngưỡng/điều kiện:** kết quả nào được xem là đạt?
- **Nguồn bằng chứng:** dữ liệu đến từ đâu?
- **Cửa sổ đánh giá:** thời điểm hoặc khoảng thời gian nào?
- **Ngoại lệ:** trường hợp nào được loại trừ và vì sao?

Ví dụ:

> Với API tạo lịch trong môi trường staging của bản phát hành R42, p95 latency phải không vượt quá 500 ms khi chạy workload 100 request/giây trong 15 phút sau giai đoạn warm-up. Số liệu lấy từ bộ đo đã đồng bộ thời gian và gắn với build ID.

Mô tả này rõ hơn “API phải nhanh”, vì nó cho biết phạm vi, cách đo, tải và ngưỡng.

### 3.2. Xác định quy tắc về dữ liệu đủ dùng

Trước khi chạy đánh giá, xác định thế nào là bằng chứng đủ:

- Số lượng mẫu tối thiểu hoặc khoảng quan sát cần thiết.
- Các nhóm hành trình, vai trò, thiết bị hoặc dữ liệu phải được bao phủ.
- Môi trường và cấu hình được chấp nhận.
- Mức độ mới của dữ liệu.
- Nguồn dữ liệu và cách xác minh tính toàn vẹn.
- Các điều kiện khiến một lần đo phải bị loại.

Không đặt ngưỡng chất lượng dữ liệu sau khi đã thấy kết quả chỉ để biến một tiêu chí chưa đạt thành đạt. Nếu cần thay đổi phương pháp hoặc ngưỡng, ghi lý do, người phê duyệt và tác động tới khả năng so sánh.

### 3.3. Phân biệt ngưỡng sản phẩm với ngưỡng bằng chứng

Hai loại ngưỡng này trả lời hai câu hỏi khác nhau:

| Loại ngưỡng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Ngưỡng chất lượng sản phẩm | Kết quả nào được chấp nhận? | p95 latency không quá 500 ms |
| Ngưỡng đủ bằng chứng | Cần dữ liệu nào để kết luận? | Có ít nhất 10.000 request hợp lệ trong workload đã định |

Nếu p95 là 700 ms trên 20.000 request hợp lệ, tiêu chí sản phẩm chưa đạt. Nếu p95 là 400 ms nhưng chỉ có 12 request do tải không được tạo đúng, chưa đủ bằng chứng để kết luận tiêu chí đạt.

## 4. Đánh giá tính hợp lệ và đầy đủ của bằng chứng

### 4.1. Kiểm tra nguồn và phạm vi

Trước khi so sánh dữ liệu với tiêu chí, xác minh:

- Dữ liệu đến từ đúng môi trường và phiên bản.
- Build ID, commit hoặc release ID khớp với đối tượng đánh giá.
- Thời gian bắt đầu và kết thúc nằm trong cửa sổ cần thiết.
- Thành phần, tenant, vai trò và hành trình thuộc phạm vi đã xác định.
- Nguồn thu thập được cấu hình đúng.
- Không có thay đổi ngoài kế hoạch làm sai lệch phép đo.

Ví dụ, số liệu latency của build R41 không thể dùng để kết luận tiêu chí của R42 nếu R42 đã thay đổi database query hoặc cấu hình cache.

### 4.2. Kiểm tra chất lượng dữ liệu

Đánh giá dữ liệu theo các chiều:

| Chiều | Câu hỏi |
| --- | --- |
| Đầy đủ | Có thiếu mẫu, trường, sự kiện hoặc khoảng thời gian không? |
| Chính xác | Giá trị có phản ánh đúng sự kiện hoặc kết quả không? |
| Nhất quán | Timestamp, ID, đơn vị và trạng thái có khớp giữa các nguồn không? |
| Hợp lệ | Dữ liệu có tuân thủ schema và quy tắc đo không? |
| Đại diện | Mẫu có phản ánh phạm vi và workload cần đánh giá không? |
| Mới | Dữ liệu có còn phù hợp với phiên bản và thời điểm hiện tại không? |
| Truy vết được | Có thể xác định nguồn, cách thu thập và lần chạy tạo ra dữ liệu không? |

Một dashboard hiển thị giá trị không đủ để khẳng định dữ liệu hợp lệ. Cần biết metric được tính từ nguồn nào, có mất mẫu không và bộ lọc có loại nhầm nhóm request quan trọng không.

### 4.3. Phân biệt không có dữ liệu với dữ liệu bằng không

Đây là lỗi diễn giải phổ biến:

- **Không có bản ghi** có thể nghĩa là chưa chạy, mất telemetry hoặc bộ lọc sai.
- **Giá trị bằng 0** có thể là một phép đo hợp lệ, ví dụ số lỗi trong một cửa sổ đã có request.
- **Không có lỗi được ghi nhận** không đồng nghĩa không có lỗi nếu hệ thống không thu thập log hoặc test chưa bao phủ hành vi đó.
- **Không có defect mở** chỉ có ý nghĩa khi defect database được đồng bộ và phạm vi truy vấn đầy đủ.

Không tự thay giá trị thiếu bằng 0. Hãy giữ trạng thái null/unknown và điều tra lý do.

### 4.4. Dữ liệu một phần có thể đủ cho một kết luận hẹp

Không phải mọi dữ liệu thiếu đều làm vô hiệu toàn bộ đánh giá. Nếu tiêu chí có thể được phân tách, nhóm có thể kết luận cho phần đã có bằng chứng và ghi phần còn thiếu.

Ví dụ, kiểm thử tương thích có 10 trình duyệt trong ma trận:

- 7 trình duyệt đã chạy với dữ liệu hợp lệ và đạt.
- 1 trình duyệt có bằng chứng vi phạm tiêu chí.
- 2 trình duyệt chưa có kết quả do thiếu thiết bị.

Kết luận phù hợp là có một phần chưa đạt và hai phần chưa đánh giá. Không nên ghi toàn bộ tiêu chí là “chưa có dữ liệu”, cũng không được ghi đạt toàn bộ ma trận.

## 5. Quy trình phân loại kết quả

~~~mermaid
flowchart TD
    A["Nhận dữ liệu đánh giá"] --> B{"Đúng phạm vi, phiên bản và nguồn?"}
    B -->|"Không"| C["Dữ liệu không hợp lệ hoặc hết hạn"]
    B -->|"Có"| D{"Đủ mẫu và độ bao phủ?"}
    D -->|"Không"| E["Chưa đủ bằng chứng"]
    D -->|"Có"| F{"Phương pháp đo đáng tin cậy?"}
    F -->|"Không"| G["Đánh giá bị chặn hoặc không hợp lệ"]
    F -->|"Có"| H{"Kết quả đáp ứng tiêu chí?"}
    H -->|"Có"| I["Đạt"]
    H -->|"Không"| J["Chưa đạt"]
    C --> K["Xác định dữ liệu cần bổ sung"]
    E --> K
    G --> K
~~~

Quy trình phân loại:

1. Xác định tiêu chí và phạm vi.
2. Kiểm tra dữ liệu có thuộc đúng đối tượng đánh giá không.
3. Kiểm tra dữ liệu có đầy đủ và đại diện theo kế hoạch không.
4. Kiểm tra phương pháp thu thập, tính toán và nguồn có hợp lệ không.
5. Chỉ khi bằng chứng đủ tin cậy mới so sánh kết quả với ngưỡng.
6. Ghi kết quả, lý do và giới hạn kết luận.
7. Nếu thiếu bằng chứng, tạo hành động bổ sung dữ liệu và người chịu trách nhiệm.

## 6. Ví dụ phân biệt trạng thái trong các tiêu chí chất lượng

### 6.1. Hiệu năng

**Tiêu chí:** p95 latency không quá 500 ms với workload đã định.

| Bằng chứng | Phân loại | Giải thích |
| --- | --- | --- |
| 20.000 request hợp lệ, p95 = 720 ms | Chưa đạt | Phép đo đủ điều kiện và vượt ngưỡng |
| Không có metric do collector ngừng hoạt động | Chưa đánh giá | Không có dữ liệu để so sánh |
| 12 request trong khi cần workload đầy đủ | Chưa đủ bằng chứng | Có dữ liệu nhưng không đại diện |
| Số liệu của bản build trước | Dữ liệu hết hạn/không đúng phạm vi | Không chứng minh chất lượng build hiện tại |
| 20.000 request, p95 = 430 ms nhưng có nhiều lỗi timeout bị loại khỏi mẫu | Cần đánh giá lại tính hợp lệ | Bộ lọc có thể làm kết quả tốt giả tạo |

### 6.2. Độ tin cậy và tỷ lệ lỗi

**Tiêu chí:** tỷ lệ request lỗi không vượt quá 0,5% trong cửa sổ quan sát đã định.

- Có 100.000 request hợp lệ và 1,2% lỗi: chưa đạt.
- Không có request hoặc metric bị mất hoàn toàn: chưa đánh giá.
- Chỉ thu được log từ một trong ba instance: dữ liệu chưa đủ bao phủ.
- Có 0 lỗi trên 5 request: chưa đủ bằng chứng để kết luận tỷ lệ lỗi đạt.

Số lỗi bằng 0 trong một mẫu nhỏ không chứng minh xác suất lỗi bằng 0. Cần xét quy mô mẫu và phương pháp đánh giá đã thống nhất.

### 6.3. Bảo mật và phân quyền

**Tiêu chí:** người dùng tenant A không thể đọc dữ liệu thuộc tenant B.

- Test có hai danh tính hợp lệ, gọi đúng endpoint và nhận dữ liệu trái quyền: chưa đạt.
- Chưa có tài khoản tenant khác để thực hiện test: bị chặn/chưa đánh giá.
- Test bị lỗi xác thực vì token hết hạn: không có bằng chứng về kiểm soát tenant.
- Test chạy đúng nhưng chỉ kiểm tra HTTP status, không kiểm tra nội dung trả về: có thể chưa đủ bằng chứng.

Nếu thiếu tài khoản test là vấn đề lặp lại, cần xử lý khả năng chuẩn bị dữ liệu và quyền. Không được đánh dấu tiêu chí bảo mật đạt chỉ vì chưa phát hiện truy cập trái phép.

### 6.4. Khả năng truy cập và tương thích

**Tiêu chí:** hành trình đăng ký phải sử dụng được bằng bàn phím và trình đọc màn hình trên các nền tảng được hỗ trợ.

- Có lỗi focus trap được tái hiện trên trình duyệt được hỗ trợ: chưa đạt cho nền tảng đó.
- Chưa có thiết bị hoặc trình đọc màn hình trong ma trận: chưa đánh giá phần tương ứng.
- Công cụ quét tự động không phát hiện lỗi nhưng chưa có kiểm tra thủ công: chỉ có bằng chứng cho phạm vi tự động, chưa đủ để kết luận toàn bộ tiêu chí.

### 6.5. Chất lượng dữ liệu

**Tiêu chí:** mọi bản ghi đơn hàng phải tham chiếu khách hàng hợp lệ.

- Kiểm tra đầy đủ dataset phát hiện bản ghi mồ côi: chưa đạt.
- Không truy cập được database để chạy kiểm tra: chưa đánh giá.
- Chỉ kiểm tra 10 trong 10.000 bản ghi theo cách chọn không đại diện: chưa đủ bằng chứng cho toàn bộ dataset.

## 7. Xử lý dữ liệu đánh giá bị thiếu hoặc không đủ

### 7.1. Xác định nguyên nhân thiếu dữ liệu

Phân loại khoảng trống trước khi chọn hành động:

| Nguyên nhân | Ví dụ | Hành động |
| --- | --- | --- |
| Chưa thực hiện | Chưa chạy test hoặc chưa có phiên đánh giá | Lập lịch và người thực hiện |
| Thiếu công cụ | Metric hoặc trace chưa được cấu hình | Bổ sung telemetry và xác minh collector |
| Môi trường không sẵn sàng | Dependency, thiết bị hoặc sandbox bị gián đoạn | Khôi phục môi trường hoặc chọn phương án được phê duyệt |
| Thiếu dữ liệu đầu vào | Không có tài khoản, dataset hoặc trạng thái cần thiết | Chuẩn bị dữ liệu và quyền |
| Thiếu phạm vi | Chưa kiểm tra một vai trò hoặc nền tảng | Mở rộng ma trận đánh giá |
| Dữ liệu không hợp lệ | Timestamp sai, ID không khớp hoặc bộ lọc sai | Sửa pipeline thu thập và chạy lại |
| Dữ liệu hết hạn | Kết quả thuộc build cũ | Thu thập lại trên phiên bản hiện tại |
| Chủ sở hữu chưa rõ | Không ai chịu trách nhiệm cung cấp kết quả | Chỉ định owner và thời hạn |

### 7.2. Tạo hành động khắc phục có thể theo dõi

Một khoảng trống cần có:

- Tiêu chí bị ảnh hưởng.
- Phần dữ liệu hoặc phạm vi còn thiếu.
- Lý do thiếu và mức độ chắc chắn.
- Rủi ro nếu tiếp tục quyết định khi chưa có dữ liệu.
- Hành động cần thực hiện.
- Người hoặc nhóm chịu trách nhiệm.
- Thời hạn hoặc mốc quyết định.
- Bằng chứng cần nộp để đóng khoảng trống.

Ví dụ: “Chưa đánh giá p95 cho build R42 vì collector không gắn build ID. Nhóm observability bổ sung nhãn build, chạy lại workload 15 phút và lưu raw sample cùng báo cáo trước thời điểm release review.”

### 7.3. Không biến khoảng trống thành ngoại lệ ngầm

Nếu một tiêu chí bắt buộc chưa có dữ liệu, không được âm thầm bỏ qua hoặc tính như đạt. Nếu tổ chức cho phép chấp nhận rủi ro hoặc miễn trừ, cần ghi:

- Tiêu chí nào được miễn.
- Phạm vi và thời hạn miễn trừ.
- Lý do và rủi ro còn lại.
- Biện pháp giảm thiểu.
- Người có thẩm quyền phê duyệt.
- Điều kiện phải đánh giá lại.

Miễn trừ là một quyết định quản trị có trách nhiệm, không phải thay đổi kết quả đo.

## 8. Quyết định chất lượng và phát hành khi thiếu bằng chứng

### 8.1. Tiêu chí chưa đạt và tiêu chí chưa đánh giá dẫn tới quyết định khác nhau

| Trạng thái | Diễn giải chất lượng | Hướng xử lý |
| --- | --- | --- |
| Đạt | Có bằng chứng đáp ứng ngưỡng | Có thể ghi nhận đạt trong phạm vi đã đánh giá |
| Chưa đạt | Có bằng chứng vi phạm ngưỡng | Khắc phục, đánh giá lại hoặc xử lý theo quy trình ngoại lệ được phê duyệt |
| Chưa đánh giá | Chưa có dữ liệu | Thu thập bằng chứng trước khi kết luận |
| Chưa đủ bằng chứng | Dữ liệu chưa đủ tin cậy hoặc bao phủ | Bổ sung mẫu, phạm vi hoặc cải thiện phương pháp |
| Bị chặn | Phụ thuộc làm đánh giá không thể thực hiện | Gỡ blocker và đánh giá lại |
| Không áp dụng | Ngoài phạm vi với lý do được chấp thuận | Lưu căn cứ và người phê duyệt |

### 8.2. Không có dữ liệu không có nghĩa là pass

Một báo cáo có nhiều tiêu chí “chưa đánh giá” không thể được diễn giải là chất lượng tốt chỉ vì chưa có lỗi nào được ghi nhận. Thiếu bằng chứng làm giảm mức độ tin cậy của quyết định.

Ngược lại, không nên tự động gắn mọi khoảng trống dữ liệu thành defect sản phẩm. Ví dụ, collector ngừng hoạt động là vấn đề về khả năng quan sát hoặc môi trường; nó làm tiêu chí chưa thể đánh giá, dù có thể bản thân khả năng quan sát cũng là một tiêu chí chất lượng riêng.

### 8.3. Phân biệt rủi ro sản phẩm với rủi ro không biết

- **Rủi ro sản phẩm đã được chứng minh:** có bằng chứng hành vi vi phạm tiêu chí.
- **Rủi ro chưa biết:** thiếu bằng chứng để xác định hành vi có đáp ứng tiêu chí không.
- **Rủi ro về quy trình đánh giá:** hệ thống không thể tạo ra hoặc giữ bằng chứng cần thiết.

Cả ba đều cần được quản lý, nhưng không nên dùng cùng một nhãn. Rủi ro chưa biết có thể quan trọng đối với quyết định phát hành, đặc biệt với bảo mật, dữ liệu, an toàn hoặc các tiêu chí bắt buộc.

### 8.4. Báo cáo kết luận theo phạm vi

Nếu chỉ một phần tiêu chí được đánh giá, hãy nêu:

- Phạm vi đã đánh giá và kết quả.
- Phạm vi chưa đánh giá.
- Chất lượng và giới hạn của dữ liệu.
- Các tiêu chí chưa đạt đã có bằng chứng.
- Các khoảng trống cần xử lý.
- Rủi ro còn lại và quyết định của người có thẩm quyền.

Tránh một nhãn tổng thể “PASS” nếu còn tiêu chí bắt buộc chưa được đánh giá mà không có quyết định ngoại lệ rõ ràng.

## 9. Quản lý trạng thái trong dashboard và báo cáo

### 9.1. Thiết kế dashboard không gây hiểu nhầm

Dashboard nên phân biệt rõ:

- Số tiêu chí đạt.
- Số tiêu chí chưa đạt.
- Số tiêu chí chưa đánh giá.
- Số tiêu chí chưa đủ bằng chứng.
- Số tiêu chí bị chặn.
- Số tiêu chí không áp dụng.

Không đưa trạng thái chưa đánh giá vào mẫu số của tỷ lệ đạt mà không công bố cách tính. Ví dụ, nếu có 8 tiêu chí đạt, 1 chưa đạt và 3 chưa đánh giá, báo cáo cần hiển thị cả ba nhóm. Tỷ lệ đạt trên 9 tiêu chí đã đánh giá là 8/9, nhưng không thể dùng con số này để tuyên bố 12 tiêu chí đều đạt.

### 9.2. Ghi nhận mẫu số và phạm vi

Khi trình bày phần trăm, phải ghi rõ:

- Tổng số tiêu chí trong phạm vi.
- Số tiêu chí đã đánh giá hợp lệ.
- Số tiêu chí đạt và chưa đạt.
- Số tiêu chí chưa đánh giá hoặc không áp dụng.
- Cách xử lý tiêu chí một phần hoặc nhiều ngưỡng.

Nếu tiêu chí có trọng số, công bố cách tính và lý do. Không dùng trọng số để làm mờ một tiêu chí bắt buộc chưa đạt.

### 9.3. Cập nhật trạng thái có kiểm soát

Mỗi lần đổi trạng thái cần lưu:

- Trạng thái trước và sau.
- Bằng chứng hoặc dữ liệu mới.
- Người cập nhật và thời điểm.
- Lý do đổi trạng thái.
- Phiên bản tiêu chí và phương pháp đánh giá.

Ví dụ, từ Insufficient evidence sang Not met chỉ hợp lệ khi có dữ liệu mới đủ tin cậy và kết quả vi phạm ngưỡng. Từ Not assessed sang Met cần có bằng chứng hợp lệ, không chỉ vì blocker đã đóng.

## 10. Ví dụ tổng hợp: quality gate trước khi phát hành

Giả sử release cần đáp ứng các tiêu chí:

| Tiêu chí | Điều kiện đạt | Kết quả thu được | Trạng thái |
| --- | --- | --- | --- |
| Unit suite | Tất cả test bắt buộc pass | 1 test nghiệp vụ fail do lỗi tính phí | Chưa đạt |
| API error rate | Không quá 0,5% | 0,2% trên workload đủ mẫu | Đạt |
| p95 latency | Không quá 500 ms | Collector không có dữ liệu cho build này | Chưa đánh giá |
| Tenant isolation | Không đọc được dữ liệu tenant khác | Test hợp lệ tái hiện truy cập trái quyền | Chưa đạt |
| Accessibility | Các hành trình bắt buộc dùng được bằng bàn phím | Chỉ mới kiểm tra tự động, thiếu kiểm tra bàn phím thủ công | Chưa đủ bằng chứng |
| Dependency scan | Không có lỗ hổng Critical chưa xử lý | Scan hoàn tất, không có Critical | Đạt |

Không thể kết luận release đạt chỉ vì có ba tiêu chí đã đạt. Có hai tiêu chí chưa đạt và hai tiêu chí chưa có đủ bằng chứng. Nhóm cần:

1. Sửa lỗi tính phí và lỗi phân quyền, sau đó chạy lại các regression test.
2. Khôi phục collector, chạy lại workload hiệu năng trên đúng build.
3. Hoàn tất kiểm tra bàn phím theo ma trận accessibility.
4. Cập nhật quality gate với bằng chứng và trạng thái mới.
5. Đưa ra quyết định phát hành theo chính sách bắt buộc và thẩm quyền đã định.

Nếu có quyết định chấp nhận một rủi ro còn lại, quyết định đó phải ghi rõ phạm vi, thời hạn và biện pháp giảm thiểu. Báo cáo vẫn giữ nguyên trạng thái bằng chứng thực tế.

## 11. Mẫu ghi nhận một tiêu chí chất lượng

~~~text
Criterion ID / tên:
Thuộc tính chất lượng:
Phạm vi và phiên bản:
Điều kiện đạt:
Phương pháp đánh giá:
Ngưỡng đủ bằng chứng:
Nguồn dữ liệu:
Cửa sổ đánh giá:

Dữ liệu thu được:
- Số lượng mẫu:
- Phạm vi đã bao phủ:
- Thời điểm:
- Build / environment:
- Tính hợp lệ và giới hạn:

Kết quả so với điều kiện đạt:
Trạng thái: Met / Not met / Not assessed / Insufficient evidence / Blocked / N/A / Stale
Lý do phân loại:
Bằng chứng / liên kết:

Khoảng trống còn lại:
Hành động tiếp theo:
Owner:
Due date:
Người phê duyệt / ngoại lệ (nếu có):
Thời điểm đánh giá lại:
~~~

## 12. Checklist phân biệt tiêu chí chưa đạt với dữ liệu đánh giá chưa có

- [ ] Tiêu chí có điều kiện đạt, phạm vi và phương pháp rõ ràng.
- [ ] Ngưỡng chất lượng sản phẩm được tách khỏi ngưỡng đủ bằng chứng.
- [ ] Dữ liệu đúng phiên bản, môi trường và cửa sổ đánh giá.
- [ ] Nguồn, schema, đơn vị và cách tính đã được xác minh.
- [ ] Số lượng mẫu và độ bao phủ đáp ứng kế hoạch.
- [ ] Dữ liệu thiếu không bị thay bằng giá trị 0 hoặc mặc định đạt.
- [ ] Kết quả vi phạm ngưỡng với bằng chứng hợp lệ được đánh dấu Not met.
- [ ] Thiếu dữ liệu, thiếu mẫu hoặc thiếu phạm vi được đánh dấu đúng trạng thái chưa đánh giá.
- [ ] Test failure do môi trường được phân biệt với defect sản phẩm.
- [ ] Phần đã đánh giá và chưa đánh giá được báo cáo riêng.
- [ ] Mọi khoảng trống có nguyên nhân, owner, hành động và thời hạn.
- [ ] Tiêu chí bắt buộc chưa có bằng chứng không bị âm thầm bỏ qua.
- [ ] Ngoại lệ hoặc chấp nhận rủi ro có thẩm quyền, phạm vi và thời hạn rõ.
- [ ] Dashboard công bố mẫu số và cách tính tỷ lệ.
- [ ] Mọi thay đổi trạng thái có bằng chứng và lịch sử truy vết.

Phân biệt tiêu chí chưa đạt với dữ liệu đánh giá chưa có giúp báo cáo phản ánh đúng điều đã biết và điều chưa biết. Khi tiêu chí, ngưỡng bằng chứng, nguồn dữ liệu và trạng thái được định nghĩa rõ, nhóm có thể đưa ra quyết định chất lượng minh bạch, tập trung đúng hành động khắc phục và tránh cả hai sai lầm: tuyên bố đạt khi chưa có căn cứ hoặc quy lỗi cho sản phẩm khi phép đánh giá chưa hợp lệ.
