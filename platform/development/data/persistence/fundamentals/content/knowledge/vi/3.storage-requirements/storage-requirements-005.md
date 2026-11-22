# Đặt yêu cầu về độ trễ và thông lượng

Một hệ thống có thể lưu dữ liệu đúng nhưng vẫn không đáp ứng nghiệp vụ: trang tìm kiếm đơn hàng mất vài giây mới xuất hiện, hoặc cơ sở dữ liệu xử lý ổn khi có 10 người dùng nhưng nghẽn khi nhiều yêu cầu cùng đến. Trước khi chọn cơ sở dữ liệu, thiết kế bảng, chỉ mục hay tầng persistence cho Java, cần mô tả **độ trễ chấp nhận được** và **khối lượng công việc hệ thống phải phục vụ** bằng những yêu cầu có thể đo và kiểm chứng.

Bài học thuộc chương **Yêu cầu lưu trữ** của module `DATA_PERSISTENCE_FUNDAMENTALS`. Việc đặt yêu cầu hiệu năng sẽ dẫn đường cho các quyết định tiếp theo về mô hình dữ liệu, truy vấn và chỉ mục, giao dịch và cô lập, kiểm soát đồng thời, quản lý kết nối Java, xử lý lỗi và retry, tiến hóa schema, bảo mật, sao lưu và tối ưu vận hành.

## 1. Độ trễ và thông lượng là hai đại lượng khác nhau

**Độ trễ (latency)** là thời gian để **một thao tác** hoàn thành, đo từ một điểm bắt đầu đến một điểm kết thúc được xác định rõ. Đơn vị thường dùng là mili giây (`ms`), đôi khi micro giây (`µs`) hoặc giây (`s`).

Ví dụ: bắt đầu tính khi API nhận yêu cầu xem đơn hàng, kết thúc khi API đã tạo xong phản hồi. Nếu mất 85 ms thì độ trễ của yêu cầu đó là 85 ms.

**Thông lượng (throughput)** là **số đơn vị công việc hoàn thành trong một khoảng thời gian**. Đơn vị phải nói rõ đối tượng được đếm:

- `requests/second` (**RPS**): số yêu cầu API hoàn tất mỗi giây.
- `transactions/second` (**TPS**): số giao dịch hoàn tất mỗi giây; cần nói rõ là giao dịch nghiệp vụ hay giao dịch database.
- `queries/second` hoặc `operations/second`: số truy vấn/thao tác trên kho dữ liệu mỗi giây.
- `MiB/s`, `MB/s`: số byte dữ liệu xử lý hoặc truyền mỗi giây. Một `MiB` bằng `1.048.576` byte, còn một `MB` bằng `1.000.000` byte.

Ví dụ: một API trả lời 600 yêu cầu đọc trong 1 giây có thông lượng 600 RPS trong giây đó. Con số này **không cho biết** từng yêu cầu chờ bao lâu: có thể phần lớn hoàn tất dưới 30 ms nhưng một số chờ 2 giây.

| Góc nhìn | Độ trễ | Thông lượng |
| --- | --- | --- |
| Câu hỏi | Một thao tác hoàn thành nhanh đến đâu? | Hệ thống hoàn thành bao nhiêu công việc mỗi giây? |
| Đơn vị | `ms`, `s` | `RPS`, `TPS`, `ops/s`, `MiB/s` |
| Giá trị quan trọng | Phân phối, p50, p95, p99, thời gian chờ đuôi | Mức tải ổn định, tải đỉnh, thông lượng bền vững |
| Rủi ro thường gặp | Một nhóm yêu cầu rất chậm dù trung bình tốt | Hệ thống nghẽn, hàng đợi tăng, lỗi/timeouts khi tải vượt khả năng |
| Cách đặt yêu cầu | “p99 độ trễ đọc không vượt 350 ms” | “Phục vụ 1.200 yêu cầu đọc mỗi giây trong 30 phút” |

**Độ trễ thấp ở tải nhẹ không chứng minh thông lượng cao.** Ngược lại, đạt nhiều RPS không có nghĩa người dùng được phản hồi đủ nhanh hoặc tỷ lệ lỗi chấp nhận được. Một yêu cầu hiệu năng tốt phải xem xét đồng thời cả hai.

## 2. Trước khi đặt con số, xác định đang đo thao tác nào

Cùng một tính năng có nhiều điểm bắt đầu và kết thúc khác nhau:

~~~mermaid
flowchart LR
    A["Client gửi yêu cầu"] --> B["API nhận yêu cầu"]
    B --> C["Chờ connection pool"]
    C --> D["DB thực thi truy vấn"]
    D --> E["Xử lý kết quả / nghiệp vụ"]
    E --> F["COMMIT nếu có ghi"]
    F --> G["API gửi phản hồi"]
    G --> H["Client nhận phản hồi"]
~~~

Có thể đo:

1. **Độ trễ cảm nhận từ client (end-to-end):** từ khi client gửi tới khi nhận được phản hồi. Bao gồm mạng và các thành phần trung gian.
2. **Độ trễ tại API:** từ lúc server nhận yêu cầu đến khi hoàn tất phản hồi, không nhất thiết bao gồm thời gian truyền trên mạng đến client.
3. **Thời gian chờ lấy kết nối:** từ lúc yêu cầu kết nối đến khi pool cấp kết nối hoặc báo hết thời gian chờ.
4. **Độ trễ của truy vấn:** thời gian thực thi truy vấn, đọc dữ liệu trả về và các thành phần được công cụ đo tính vào.
5. **Độ trễ giao dịch ghi:** từ lúc bắt đầu giao dịch đến khi `COMMIT` trả kết quả hoặc lỗi, gồm những lần chờ và truy vấn liên quan.

Nếu chỉ đo thời gian chạy một câu `SELECT` mà không đo chờ kết nối, serialize phản hồi và chờ transaction, có thể kết luận sai rằng API rất nhanh.

Cần ghi rõ **đơn vị công việc**: “lấy chi tiết một đơn hàng theo ID” khác hoàn toàn “liệt kê 10.000 đơn hàng kèm toàn bộ dòng hàng”. Ngay cả cùng một câu SQL, độ trễ có thể khác theo số bản ghi, độ chọn lọc, dữ liệu đã nằm trong cache hay chưa và số truy vấn phát sinh từ ORM.

### Phân biệt ba mốc thời gian trong thao tác ghi

Với nghiệp vụ tạo đơn hàng, có thể có các mốc:

- Java đã tạo đối tượng hoặc gọi `save()`.
- ORM đã gửi lệnh SQL, hoặc JDBC đã trả kết quả cho từng câu lệnh.
- **Transaction đã được xác nhận bằng `COMMIT`** theo bảo đảm của cơ sở dữ liệu.

Nếu yêu cầu là “lưu thành công và có thể đọc lại theo hợp đồng nhất quán đã công bố”, độ trễ cần đo đến mốc tương ứng, thường là sau khi giao dịch được xác nhận. `flush()` của ORM không thay thế `COMMIT`. Nếu hệ thống trả phản hồi trước khi lưu xong theo mô hình bất đồng bộ, phải tách **thời gian chấp nhận yêu cầu** khỏi **thời gian hoàn tất lưu bền vững** thành hai chỉ tiêu riêng.

## 3. Độ trễ phải được mô tả bằng phân phối

Độ trễ dao động theo tải, dữ liệu, trạng thái cache, mạng, tranh chấp khóa và các hoạt động nền. Bởi vậy “trung bình dưới 100 ms” thường chưa đủ.

Giả sử có 100 yêu cầu:

- 95 yêu cầu hoàn tất trong khoảng 40–80 ms.
- 4 yêu cầu mất 200–350 ms.
- 1 yêu cầu mất 2.000 ms.

Dù số đông nhanh, một người dùng vẫn có thể phải chờ 2 giây. Để nhìn thấy phần đuôi chậm, dùng các **phân vị (percentiles)**:

| Chỉ số | Cách hiểu thực tế |
| --- | --- |
| `p50` (median) | Khoảng 50% mẫu có độ trễ không cao hơn giá trị p50 theo phương pháp tính đã chọn. |
| `p95` | Khoảng 95% mẫu không cao hơn giá trị này, còn khoảng 5% chậm hơn. |
| `p99` | Khoảng 99% mẫu không cao hơn giá trị này, còn khoảng 1% chậm hơn. |
| `p99.9` | Tập trung vào phần đuôi rất hiếm; cần đủ mẫu và phép đo phù hợp mới có ý nghĩa. |
| Trung bình | Có ích cho phân tích tổng tải và tổng thời gian, nhưng có thể che khuất các yêu cầu rất chậm. |

Ví dụ một SLO đọc là **`p99 ≤ 350 ms`**, nghĩa là trong tập yêu cầu **hợp lệ, thuộc phạm vi đo, tại cửa sổ và mức tải được chỉ định**, ít nhất khoảng 99% hoàn thành trong 350 ms theo phương pháp phân vị đã thống nhất. Đó **không** có nghĩa mọi yêu cầu đều phải dưới 350 ms.

Khi đặt SLO:

- Chọn phạm vi: từng API, thao tác đọc/ghi, hoặc nhóm giao dịch có hành vi tương đồng; tránh gộp yêu cầu nhanh và chậm rồi lấy một con số tổng.
- Chọn cửa sổ: 5 phút để quan sát, 30 phút dưới tải đỉnh để kiểm thử, hoặc 30 ngày cho SLO vận hành; mỗi mục đích khác nhau.
- Chỉ rõ mẫu thành công và lỗi được tính thế nào. Nếu chỉ thu thập latency cho request thành công, hệ thống có thể “đẹp số” vì nhiều request quá chậm đã timeout và bị loại.
- Đo cả **tỷ lệ lỗi và timeout** bên cạnh latency; yêu cầu hiệu năng chưa đạt nếu nhanh nhưng thất bại nhiều.
- Với tỷ lệ mẫu ít, p99/p99.9 có thể biến động mạnh. Không đánh giá p99 từ vài chục yêu cầu rồi suy ra tính ổn định của hệ thống.
- Dùng histogram hoặc công cụ phân phối phù hợp; **không lấy trung bình các giá trị p99 của nhiều máy hoặc nhiều khoảng thời gian** để tính p99 toàn hệ thống.

## 4. Xác định khối lượng công việc trước khi định nghĩa thông lượng

Một mức `1.000 RPS` trống ngữ cảnh ít có giá trị. Cần biết “1.000 yêu cầu gì” và tỷ lệ công việc.

Ví dụ đối với hệ thống bán hàng:

| Loại công việc | Dữ liệu thao tác | Khuôn mẫu truy cập | Yếu tố có thể chi phối độ trễ |
| --- | --- | --- | --- |
| Xem chi tiết đơn hàng | Đọc 1 đơn, các dòng hàng và trạng thái | Đọc nhiều; lọc theo ID | Chỉ mục, số câu SQL, ORM N+1, kích thước kết quả |
| Xem lịch sử đơn hàng | Đọc danh sách phân trang | Lọc theo khách hàng, sắp theo thời gian | Pagination, chỉ mục ghép, số lượng hàng |
| Tạo đơn hàng | Ghi đơn và nhiều dòng hàng | Transaction gồm nhiều câu lệnh | Khóa, ràng buộc, WAL, commit, retry |
| Cập nhật tồn kho | Đọc/ghi dữ liệu nóng | Nhiều yêu cầu cùng sửa một mã hàng | Tranh chấp khóa, version, mức cô lập |
| Đồng bộ báo cáo | Đọc hoặc tổng hợp dữ liệu lớn | Tác vụ nền | I/O và CPU có thể cạnh tranh với API |

Các tham số cần khảo sát:

**Tỷ lệ đọc/ghi.** Nếu 90% là đọc và 10% là ghi, giải pháp tối ưu cho việc cập nhật liên tục chưa chắc phù hợp. Cần cân nhắc yêu cầu nhất quán của đọc sau ghi và khả năng cache.

**Kích thước dữ liệu.** Một yêu cầu trả 1 KB và một yêu cầu tải 5 MB có thể cùng được tính là một RPS, nhưng chi phí băng thông và bộ nhớ khác xa.

**Phân phối truy cập.** Đọc một số mã hàng cực kỳ phổ biến sẽ tạo **hot keys/hot rows**; dữ liệu phân bố đều cho kết quả thử nghiệm khác. Nên xét cả dữ liệu mới, dữ liệu cũ và truy vấn hiếm.

**Số bước xử lý.** Một API có thể tạo 1 câu SQL, 10 câu SQL hoặc một transaction gồm hàng chục cập nhật. Cần ước lượng mức khuếch đại từ API RPS sang DB ops/s và các lần ghi đĩa.

**Mức tải theo thời gian.** Ghi rõ tải bình thường, tải giờ cao điểm, đột biến ngắn và thời lượng chịu tải liên tục; một mức burst 10 giây khác với duy trì liên tục 30 phút.

**Dữ liệu tích lũy.** Tập dữ liệu sản xuất có thể tăng từ 100 nghìn lên 50 triệu bản ghi. Kiểm thử với bảng có 100 hàng không thể thay thế kiểm thử ở quy mô dự kiến.

### Thông lượng được đo ở đâu?

Nên phân biệt:

- **Offered load**: số yêu cầu được client gửi đến mỗi giây.
- **Completed throughput**: số yêu cầu thực sự hoàn tất mỗi giây.
- **Successful throughput**: số yêu cầu hoàn tất thành công và đáp ứng định nghĩa thành công mỗi giây.

Ví dụ bộ phát tải gửi 1.500 yêu cầu/giây nhưng hệ thống chỉ hoàn tất 1.000 yêu cầu/giây, còn lại đang chờ hoặc timeout. Không được báo cáo “hệ thống đạt 1.500 RPS” chỉ vì client đã gửi với tốc độ đó. Khi lượng yêu cầu đến lớn hơn năng lực phục vụ bền vững, hàng đợi sẽ tăng và latency đuôi thường xấu đi.

## 5. Một bộ yêu cầu mẫu đủ để kiểm chứng

Giả sử nhóm phát triển một API đơn hàng Java dùng cơ sở dữ liệu quan hệ. Các con số sau **chỉ là ví dụ về cách viết yêu cầu**, không phải chuẩn áp dụng cho mọi hệ thống.

| Hạng mục | Đọc chi tiết đơn hàng | Tạo đơn hàng |
| --- | --- | --- |
| Đơn vị đo | Một yêu cầu `GET /orders/{id}` hợp lệ | Một yêu cầu `POST /orders` với 1–5 dòng hàng |
| Tải bình thường | 400 yêu cầu/giây | 80 yêu cầu/giây |
| Tải đỉnh cần chịu | 1.200 yêu cầu/giây | 250 yêu cầu/giây |
| Thời gian tải đỉnh | Duy trì **30 phút**, đo sau giai đoạn khởi động tải | Duy trì **30 phút**, đo sau giai đoạn khởi động tải |
| SLO p95 tại API | ≤ 120 ms | ≤ 300 ms |
| SLO p99 tại API | ≤ 350 ms | ≤ 800 ms |
| Tỷ lệ lỗi hệ thống | ≤ 0,1% trong cửa sổ kiểm thử | ≤ 0,1% trong cửa sổ kiểm thử |
| Mốc hoàn thành | Hoàn thành phản hồi từ API | Giao dịch tạo đơn đã commit và API hoàn thành phản hồi |
| Điều kiện dữ liệu | Khoảng 5 triệu đơn, đọc cả dữ liệu phổ biến và ít gặp | Ràng buộc khóa ngoại, tồn kho, số lượng dòng hàng thực tế |

Các giả định chung: tải đỉnh **đọc và ghi diễn ra đồng thời**; một cửa sổ kiểm thử kéo dài 30 phút; dữ liệu đã có phân phối gần sản xuất; xác định rõ phiên bản ứng dụng, tài nguyên triển khai, cấu hình database, network và connection pool. Mức lỗi 0,1% cần được hiểu là lỗi hệ thống (ví dụ 5xx, timeout); lỗi validation do input sai được thống kê riêng, không dùng để che lỗi hệ thống.

Để trở thành tiêu chí chấp nhận, cần bổ sung:

1. **Nguồn đo:** latency tại server hay client; collection từ API, tracing hay load generator.
2. **Cách lấy mẫu:** có đo đầy đủ mọi yêu cầu hay lấy mẫu; loại trừ warm-up; tính phân vị theo phương pháp nào.
3. **Phạm vi thành công:** request nhận phản hồi thành công nhưng thay đổi chưa commit có được tính hay không.
4. **Yêu cầu dữ liệu đúng:** không tạo trùng đơn, không mất cập nhật tồn kho, không có giao dịch thành công nhưng thiếu bản ghi.
5. **Điều kiện kết thúc:** thời gian tải liên tục, hàng đợi/connection pool có ổn định hay không, có tồn đọng sau khi ngừng phát tải không.

Có thể phát biểu cô đọng một tiêu chí như sau:

> Trong môi trường kiểm thử cấu hình X, với 5 triệu đơn hàng và tải đồng thời 1.200 lần đọc cùng 250 lần tạo đơn mỗi giây trong 30 phút sau warm-up, API đọc phải đạt p99 ≤ 350 ms, API tạo đơn p99 ≤ 800 ms; tỷ lệ lỗi hệ thống của mỗi nhóm ≤ 0,1%, không làm mất hoặc tạo trùng dữ liệu nghiệp vụ.

Đây mới là **mục tiêu được đề xuất**. Chỉ sau đo kiểm phù hợp mới biết giải pháp có đạt hay không.

## 6. Ước lượng tải và mức đồng thời

Khi ước tính quy mô, có thể chuyển từ yêu cầu ở API sang chi phí phía dưới.

### Từ RPS sang số thao tác database

Với tải đỉnh ở ví dụ:

- `1.200` yêu cầu đọc/giây, giả sử trung bình mỗi lần thực hiện `1` truy vấn SQL.
- `250` yêu cầu tạo đơn/giây, giả sử trung bình mỗi lần thực hiện `4` lệnh SQL.
- Tổng ước tính **`1.200 + 250 × 4 = 2.200` câu lệnh SQL/giây**.

Đây là phép **ước tính chi phí logic**, không phải đo thông lượng tối đa của database. Truy vấn có chi phí khác nhau; một `JOIN` phức tạp không tương đương một `SELECT` theo khóa chính. Ngoài ra còn có commit, các truy vấn ORM phát sinh, truy cập cache, lock, checkpoint, replica và background job.

Nếu kết quả đo đạt 2.200 lệnh/giây nhưng CPU/đĩa đã gần bão hòa, hệ thống không còn nhiều khả năng xử lý burst, failover hay tải nền. Mức dự phòng phải được quyết định bằng thử nghiệm ở đúng môi trường và rủi ro, không thể suy ra chắc chắn từ một tỷ lệ cố định.

### Từ lưu lượng phản hồi sang băng thông

Nếu trung bình phản hồi đọc có payload 4 KiB, thì riêng payload chiều trả về của 1.200 yêu cầu đọc/giây tạo ra khoảng:

`1.200 × 4 KiB = 4.800 KiB/s ≈ 4,69 MiB/s.`

Con số **chưa tính** header, giao thức, nén, dữ liệu yêu cầu gửi lên, truy vấn nội bộ, bản sao và các kết nối khác. Nếu payload tăng gấp 10, áp lực mạng và memory buffer cũng thay đổi dù RPS giữ nguyên.

### Định luật Little: thông lượng, thời gian và lượng công việc đang xử lý

Với hệ thống ổn định, định luật Little diễn đạt:

`L = λ × W`

Trong đó:

- `L`: số công việc trung bình đang nằm trong hệ thống.
- `λ`: tốc độ hoàn thành trung bình (công việc/giây), bằng tốc độ đến trung bình khi hệ thống ổn định.
- `W`: thời gian trung bình một công việc ở trong hệ thống (giây).

Ví dụ, nếu một API đạt **750 yêu cầu/giây** với **thời gian trung bình 0,12 giây**, thì số yêu cầu trung bình đang trong phạm vi đo xấp xỉ:

`750 × 0,12 = 90 yêu cầu đồng thời.`

**Không suy ra connection pool phải có đúng 90 kết nối.** Một request có thể chờ CPU, mạng hoặc xử lý nghiệp vụ ngoài database, và chỉ giữ kết nối trong một phần vòng đời request. Cần đo riêng thời gian chiếm kết nối, tải DB và thời gian chờ pool để chọn kích thước pool. Mở pool quá lớn có thể làm tăng tranh chấp và khiến database chậm hơn.

Định luật Little dùng **giá trị trung bình dưới điều kiện ổn định**; không thay thời gian trung bình bằng p99 để tính số request đồng thời. Khi hệ thống đang tích hàng đợi ngày càng dài, điều kiện ổn định không còn phù hợp.

## 7. Dùng ngân sách độ trễ để phân tích nút thắt

Nếu API đọc có yêu cầu p99 ≤ 350 ms, việc chia ngân sách có thể hỗ trợ thiết kế:

| Công đoạn | Ngân sách dự kiến để phân tích |
| --- | ---: |
| Chờ connection pool | 30 ms |
| Database thực thi, trả dữ liệu | 180 ms |
| Logic ứng dụng và ánh xạ kết quả | 70 ms |
| Serialize và tạo phản hồi | 30 ms |
| Dự phòng cho dao động/phần khác | 40 ms |
| **Tổng ngân sách minh họa** | **350 ms** |

Các mức trên là **mục tiêu phân bổ để phân tích**, không phải số đo và không phải bảo đảm thống kê. **Không được cộng các giá trị p99 của từng công đoạn rồi mặc định kết quả là p99 toàn bộ request**; các phân vị trên các phân phối khác nhau không cộng tuyến tính như thời gian của một request cụ thể. Muốn xác nhận SLO cần đo **toàn bộ yêu cầu** trong cùng phép thử.

Dùng tracing/metrics để trả lời:

- Chờ lấy kết nối lâu vì pool quá nhỏ hay vì transaction giữ kết nối quá lâu?
- SQL mất thời gian vì thiếu index, quét nhiều hàng, khóa hay I/O?
- JPA/Hibernate có tạo nhiều truy vấn N+1 cho một API không?
- Việc serialize JSON có xử lý một object graph rất lớn không?
- Có nhiều transaction cùng chạm vào một bản ghi “nóng” không?
- Thời gian `COMMIT` có tăng khi hệ lưu trữ phải bảo đảm durability hay replication đồng bộ không?

Điểm cần tối ưu là **đường thực thi thực tế**, không nhất thiết là dòng Java dễ nhìn nhất.

## 8. Các ràng buộc persistence ảnh hưởng đến độ trễ

### Truy vấn và chỉ mục

Bảng lớn nhưng thiếu index phù hợp khiến truy vấn lọc và sắp xếp phải đọc nhiều dữ liệu. Chỉ mục trên đúng các trường thường dùng có thể giảm thời gian truy vấn, nhưng cũng làm tăng chi phí `INSERT`, `UPDATE` và dung lượng lưu trữ. Cần quan sát execution plan và số hàng đọc thực tế trước khi thêm index.

### Giao dịch, cô lập và kiểm soát đồng thời

Giao dịch dài có thể giữ lock và kết nối lâu, khiến thời gian chờ của các yêu cầu khác tăng. Mức cô lập cao hơn có thể thay đổi khả năng đồng thời hoặc cách hệ quản trị xử lý xung đột. Không nên giảm mức cô lập chỉ để đạt chỉ tiêu latency nếu đánh đổi bằng lost update hoặc sai lệch nghiệp vụ.

### Durability, đồng bộ và replication

Các cơ chế như write-ahead logging, flush, checkpoint và xác nhận từ bản sao có thể ảnh hưởng độ trễ ghi. Mức bảo đảm lưu bền cần được chỉ định **trước** khi so sánh kết quả benchmark; một cấu hình trả lời sớm nhưng có thể mất các giao dịch gần nhất không tương đương cấu hình yêu cầu durability mạnh hơn.

### Connection pool và giới hạn tài nguyên

Tăng kích thước pool không đồng nghĩa tăng thông lượng vô hạn. Database có giới hạn CPU, I/O, bộ nhớ và số tác vụ thực thi hiệu quả; quá nhiều kết nối đồng thời đôi khi làm tăng context switching, contention và độ trễ đuôi. Theo dõi số kết nối đang dùng, chờ lấy kết nối và timeout.

### Cache và tính nhất quán

Cache có thể giảm độ trễ đọc, nhưng dữ liệu có thể cũ. Một SLO đọc “tài khoản cập nhật ngay sau chuyển tiền” phải đi kèm yêu cầu tính nhất quán. Số liệu lấy từ cache nóng và số liệu khi cache miss/cold start nên được đo riêng và theo đúng tỷ lệ sản xuất.

### Backup, migration và tải nền

Backup, tạo index, migration và batch job có thể gây I/O hoặc khóa làm ảnh hưởng yêu cầu trực tuyến. Một hệ thống chỉ đạt SLO khi không có công việc nền chưa chắc đáp ứng vận hành thực tế. Cần kiểm thử các tình huống hợp lý tương ứng với lịch vận hành.

## 9. Đo độ trễ của mã Java theo đúng ranh giới

Java có thể dùng `System.nanoTime()` để đo khoảng thời gian đã trôi qua (elapsed time). Không dùng `System.currentTimeMillis()` để đo khoảng thời gian ngắn vì nó biểu diễn thời gian đồng hồ và có thể bị điều chỉnh.

Ví dụ đo một thao tác đọc bằng JDBC, bao gồm thời gian lấy kết nối, chuẩn bị lệnh, chạy SQL, lấy hàng kết quả và đóng tài nguyên:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.OptionalLong;
import javax.sql.DataSource;

interface LatencyMetrics {
    void recordNanos(String operation, long elapsedNanos);
}

final class AccountReader {
    private final DataSource dataSource;
    private final LatencyMetrics metrics;

    AccountReader(DataSource dataSource, LatencyMetrics metrics) {
        this.dataSource = dataSource;
        this.metrics = metrics;
    }

    OptionalLong loadPoints(long accountId) throws SQLException {
        long started = System.nanoTime();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                 "SELECT points FROM point_accounts WHERE account_id = ?")) {

            statement.setLong(1, accountId);

            try (ResultSet rows = statement.executeQuery()) {
                return rows.next()
                    ? OptionalLong.of(rows.getLong("points"))
                    : OptionalLong.empty();
            }
        } finally {
            metrics.recordNanos(
                "account.read.total",
                System.nanoTime() - started
            );
        }
    }
}
~~~

`LatencyMetrics` là **giao diện minh họa**, cần được nối với hệ metrics thực tế (ví dụ histogram trong Micrometer/Prometheus hoặc công cụ tương ứng). `finally` ghi độ trễ cả khi JDBC phát sinh lỗi; hệ đo thực tế cũng phải gắn trạng thái thành công/thất bại và phân loại lỗi. Phần triển khai metrics phải tránh làm thay đổi hành vi exception nghiệp vụ hoặc tạo overhead đáng kể.

Đoạn mã trên đo **thời gian persistence phía Java**, chưa đo cả HTTP request hoặc thời gian mạng đến client. Muốn chẩn đoán chi tiết, cần bổ sung timer cho **chờ connection pool**, **thực thi SQL**, **thời gian commit** và **toàn bộ API** tại những ranh giới cụ thể. Cần dùng đơn vị và tên metric nhất quán, đồng thời tránh gắn nhãn có số ID cá nhân hoặc giá trị biến thiên rất lớn khiến số chuỗi metrics bùng nổ.

### Phân tách đo khi dùng ORM

Khi ứng dụng dùng JPA/Hibernate, gọi `repository.findById()` không nhất thiết chỉ thực thi một truy vấn: tùy mapping và chiến lược fetch có thể phát sinh thêm SQL. Tương tự, `entityManager.persist()` có thể chưa ghi SQL cho đến lúc `flush()`. Vì vậy, phải đối chiếu latency của service với số lượng SQL thực thi và mốc transaction commit thực tế. Đừng coi “hàm repository trả về nhanh” là bằng chứng rằng dữ liệu đã lưu bền vững.

## 10. Quy trình kiểm thử tải có thể tái lập

Một quy trình kiểm thử hữu ích:

1. **Chốt mục tiêu và phạm vi.** Ghi rõ API/thao tác, p95/p99, RPS/TPS, tỷ lệ lỗi, thời lượng, dữ liệu và điều kiện kết thúc.
2. **Chuẩn bị môi trường đại diện.** Ghi lại cấu hình ứng dụng, Java runtime, database, index, pool, mạng, tài nguyên máy, cơ chế durability và số lượng replica.
3. **Tạo dữ liệu đúng quy mô và phân phối.** Không chỉ dùng dữ liệu giả quá nhỏ hoặc toàn truy vấn theo khóa mới; cần mô phỏng hot key, dữ liệu cũ và các tỷ lệ đọc/ghi thực tế.
4. **Khởi động tải (warm-up).** Cho JIT, connection pool và cache đi qua giai đoạn khởi động; ghi riêng số liệu cold start nếu đó là yêu cầu nghiệp vụ.
5. **Chạy tải bình thường, tăng dần và đỉnh.** Ví dụ kiểm tra 400/80 RPS, rồi tăng đến 1.200/250 RPS và giữ 30 phút. Bảo đảm bộ phát tải đủ công suất, không trở thành nút thắt.
6. **Thu cùng lúc latency, throughput, errors và tài nguyên.** Đo p50/p95/p99, RPS thành công, timeout, DB CPU, IOPS, queue depth, pool wait, số SQL/request, lock wait, GC và transaction duration.
7. **Kiểm tra tính đúng đắn.** So sánh số đơn hàng, số lần xử lý request ID, số dư hoặc tồn kho để phát hiện ghi trùng, lost update, transaction lỗi hoặc trạng thái không nhất quán.
8. **Lặp lại trong cùng điều kiện và so sánh.** Ghi cấu hình, dữ liệu, kết quả và biến động giữa các lần. Sau đó kiểm tra các kịch bản vận hành quan trọng như cache miss, sự cố replica, backup, chuyển đổi schema hoặc giới hạn băng thông.

### Chú ý cách phát tải và đo latency

**Closed-loop load test:** client thường gửi yêu cầu mới sau khi yêu cầu trước kết thúc. Khi hệ thống chậm, tốc độ gửi có thể tự giảm; phép thử dễ đánh giá thấp áp lực khi lưu lượng thực đến độc lập với tốc độ phản hồi.

**Open-loop/constant-arrival-rate test:** client cố gắng gửi theo tốc độ đến đã định, ngay cả khi các request trước còn chờ. Cách này phù hợp hơn khi cần chứng minh khả năng chịu một mức offered load xác định, nhưng phải thiết kế generator đủ tài nguyên và giới hạn tải an toàn cho môi trường thử nghiệm.

Tránh **coordinated omission**: nếu hệ đo chỉ ghi các lần gọi đã được bộ phát tải hoàn tất và vô tình bỏ qua khoảng chờ đáng ra phải có các yêu cầu tiếp theo, số liệu tail latency có thể tốt hơn tình huống người dùng thực gặp. Chọn công cụ và cấu hình có khả năng đo hoặc hiệu chỉnh hiện tượng này khi cần.

Không chỉ đo tốc độ “đã gửi”; phải đo **đã hoàn tất**, **thành công**, **timeout** và **số request còn tồn đọng**. Một bài kiểm thử đạt mốc RPS nhưng tồn hàng đợi lớn sau khi dừng tải thì chưa chứng minh khả năng phục vụ bền vững.

## 11. Timeout, retry và khả năng duy trì SLO

Khi hệ thống quá tải, timeout và retry có thể khiến vấn đề nghiêm trọng hơn:

~~~mermaid
flowchart TD
    A["Tải tăng"] --> B["DB hoặc pool xuất hiện hàng đợi"]
    B --> C["Latency và timeout tăng"]
    C --> D["Client thử lại"]
    D --> E["Lưu lượng thực tế tăng thêm"]
    E --> B
~~~

Để tránh vòng lặp:

- **Timeout:** chọn giới hạn thời gian có chủ đích cho HTTP, pool, statement và transaction theo ngân sách end-to-end; tránh một bước đợi lâu hơn toàn bộ hạn phản hồi.
- **Retry:** chỉ thử lại lỗi có tính chất tạm thời và khi thao tác an toàn để thử lại; dùng giới hạn số lần, exponential backoff và jitter. Với yêu cầu ghi, thiết kế idempotency trước khi cho phép retry tự động.
- **Giới hạn tải:** cân nhắc backpressure, giới hạn đồng thời hoặc từ chối có kiểm soát khi vượt năng lực; công bố rõ tỷ lệ lỗi và phạm vi SLO.
- **Bảo toàn dữ liệu:** không bỏ bớt kiểm tra ràng buộc, xác nhận giao dịch hay yêu cầu độ bền chỉ để đạt con số latency.
- **Sự cố kéo dài:** xác định mức phục vụ suy giảm chấp nhận được và chính sách phục hồi; SLO vận hành có thể khác chỉ tiêu benchmark bình thường.

Một yêu cầu “p99 dưới 350 ms” không có nghĩa chỉ cần đặt timeout 350 ms: khi đó mọi request quá chậm có thể thành lỗi và p99 của nhóm thành công sẽ trông đẹp. **Latency, timeout và error rate phải được đánh giá cùng nhau.**

## 12. Mẫu đặc tả yêu cầu có thể dùng cho dự án

Trước khi nhóm Java thiết kế persistence, có thể điền một bảng cho mỗi thao tác quan trọng:

| Trường cần chốt | Câu hỏi phải trả lời |
| --- | --- |
| Nghiệp vụ | Đang đọc chi tiết, tìm kiếm, tạo mới, cập nhật hay xử lý batch? |
| Ranh giới đo | Client end-to-end, API server, một SQL hay cả transaction đến commit? |
| Kiểu tải | Đọc/ghi, số bản ghi, kích thước payload, số SQL/transaction, hot key? |
| Dữ liệu thử nghiệm | Số bản ghi, tuổi dữ liệu, index, phân phối, tăng trưởng dự kiến? |
| Thông lượng | RPS/TPS/ops/s mục tiêu ở tải bình thường và đỉnh? |
| Độ trễ | p50/p95/p99 hoặc ngưỡng khác, tại mức tải và cửa sổ nào? |
| Sẵn sàng và lỗi | Timeout và tỷ lệ lỗi chấp nhận; xử lý retry, yêu cầu trùng ra sao? |
| Đúng đắn | Mức cô lập, read-after-write, durability, transaction và dữ liệu bất biến? |
| Môi trường | Tài nguyên, vùng mạng, loại database, pool, replica, cache, backup? |
| Cách xác minh | Công cụ phát tải, metrics, histogram, kiểm tra dữ liệu, số lần lặp? |

Ví dụ một đặc tả ngắn cho thao tác tạo đơn:

> Với request tạo đơn hợp lệ gồm tối đa 5 dòng hàng, tại môi trường staging cấu hình giống môi trường mục tiêu và kho dữ liệu có 5 triệu đơn, hệ thống phải xử lý 250 yêu cầu tạo đơn/giây đồng thời với 1.200 yêu cầu đọc/giây trong 30 phút sau warm-up. Đo từ khi API nhận request đến khi transaction tạo đơn commit và phản hồi hoàn tất. Yêu cầu tạo đơn phải đạt p95 ≤ 300 ms, p99 ≤ 800 ms, tỷ lệ lỗi hệ thống ≤ 0,1%; mỗi request ID tạo tối đa một đơn nghiệp vụ. Kết quả đo cần kèm thông lượng hoàn tất, timeout, số yêu cầu tồn đọng và chỉ số tài nguyên database.

Các con số trong mẫu chỉ mang tính ví dụ; nhóm phải điều chỉnh theo dữ liệu sử dụng thực tế, yêu cầu nghiệp vụ, nguồn lực và đặc tính hạ tầng.

## 13. Những nhầm lẫn thường gặp

**“Trung bình 40 ms nghĩa là người dùng nào cũng thấy nhanh.”** Không. Một nhóm nhỏ yêu cầu có thể mất hàng giây; cần phân vị và tỷ lệ timeout.

**“1.000 RPS tương đương 1.000 SQL/s.”** Không. Một request có thể không truy cập database hoặc gọi hàng chục câu SQL; một transaction có thể chứa nhiều thao tác.

**“Tăng connection pool sẽ tăng throughput.”** Không chắc. Nếu DB đã quá tải, nhiều kết nối có thể làm contention và tail latency tăng.

**“Benchmark bằng bảng 100 dòng chứng minh đáp ứng bảng 100 triệu dòng.”** Không. Dung lượng, chỉ mục, phân phối khóa và caching ảnh hưởng lớn.

**“Chỉ cần đủ throughput, độ trễ sẽ tự tốt.”** Sai. Khi gần bão hòa, throughput có thể giữ tương đối ổn trong khi hàng đợi và p99 tăng mạnh.

**“Giảm yêu cầu durability giúp đạt SLO mà không có đánh đổi.”** Sai. Các mức bảo đảm về mất dữ liệu, replica và xác nhận commit phải phù hợp với nghiệp vụ.

**“Tính p99 toàn hệ thống bằng cách lấy trung bình p99 của từng máy.”** Sai. Cần kết hợp số liệu phân phối hoặc histogram theo phương pháp được công cụ hỗ trợ.

**“Request timeout là không thành công nên không cần đo latency.”** Sai. Timeout là tín hiệu quan trọng về trải nghiệm, năng lực và rủi ro retry.

## 14. Bài tập thực hành và câu hỏi tự kiểm tra

**Câu 1.** Hệ thống hoàn thành 6.000 yêu cầu trong 10 giây, trong đó 5.700 yêu cầu thành công, 300 yêu cầu lỗi. Offered load là 800 RPS. Hãy tính thông lượng hoàn tất, thông lượng thành công và giải thích vì sao không thể tuyên bố hệ thống đạt 800 RPS.

**Đáp án:** Thông lượng hoàn tất là `6.000 / 10 = 600 RPS`, thành công là `5.700 / 10 = 570 RPS`. `800 RPS` là tải đưa vào, không phải tốc độ hoàn tất. Nếu tải duy trì và hàng đợi tăng, hệ thống không chứng minh được khả năng ổn định ở offered load này.

**Câu 2.** Một API có p50 = 35 ms và p99 = 1.800 ms khi tải đỉnh, trung bình 65 ms. Chỉ số nào nói rằng một số yêu cầu chậm đáng kể?

**Đáp án:** p99 = 1.800 ms cho thấy khoảng 1% mẫu nằm ở phần đuôi gần hoặc trên mức 1,8 giây tùy phương pháp tính phân vị; cần kiểm tra timeout và phân phối latency. Trung bình 65 ms không thể hiện đầy đủ trải nghiệm của nhóm chậm.

**Câu 3.** Với 900 request/giây và thời gian trung bình end-to-end 0,2 giây trong trạng thái ổn định, số request đang trong hệ thống trung bình khoảng bao nhiêu?

**Đáp án:** Theo Little, `L = 900 × 0,2 = 180` request. Không đồng nghĩa cần 180 kết nối database, vì thời gian giữ kết nối thường chỉ là một phần thời gian request.

**Câu 4.** API ghi phản hồi “thành công” ngay khi thông điệp được đưa vào hàng đợi, còn lưu dữ liệu database diễn ra về sau. Độ trễ phản hồi API có đủ để xác nhận SLO lưu bền vững không?

**Đáp án:** Không. Phải tách SLO **chấp nhận yêu cầu** với SLO **hoàn tất lưu bền vững**, đo cả trường hợp tác vụ lỗi hoặc bị retry và quy định client được bảo đảm điều gì.

**Câu 5.** Một bài kiểm thử đạt p99 thấp khi chỉ đọc dữ liệu đã có trong cache. Vậy có thể áp dụng kết luận đó cho yêu cầu đọc sau khi cache bị xóa không?

**Đáp án:** Không. Cache miss thay đổi số truy vấn và I/O; cần kiểm thử theo tỷ lệ cache hit/miss thực tế và kịch bản cold start nếu nằm trong yêu cầu.

**Bài thực hành:** Hãy chọn một tính năng quản lý đơn hàng trong Java, gồm đọc chi tiết, tạo đơn và cập nhật tồn kho. Viết bản yêu cầu có đủ tải bình thường và đỉnh, p95/p99 từng thao tác, ranh giới đo đến commit, dữ liệu và thời lượng test, tỷ lệ lỗi, cơ chế retry và kiểm tra tính đúng đắn. Đề xuất các metrics lấy ở API, JDBC/ORM, connection pool và database. Sau khi có kết quả benchmark, xác định bước nào gây p99 cao và đề xuất một thay đổi cụ thể có cách đo lại.

Trong thiết kế persistence, **độ trễ** mô tả thời gian phục vụ một công việc, còn **thông lượng** mô tả lượng công việc hoàn thành theo thời gian. Một yêu cầu có giá trị phải chỉ rõ **thao tác, ranh giới đo, phân vị, tốc độ tải, thời lượng, dữ liệu, điều kiện vận hành và mức đúng đắn cần bảo toàn**. Khi những yếu tố này được đo nhất quán, nhóm Java mới có thể lựa chọn kho dữ liệu, truy vấn, chỉ mục, giao dịch và tài nguyên dựa trên bằng chứng.
