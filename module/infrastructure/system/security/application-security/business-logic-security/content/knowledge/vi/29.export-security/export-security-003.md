# Giới hạn kích thước xuất dữ liệu (Export size restriction)

Một yêu cầu xuất có thể đúng quyền nhưng vẫn gây cạn bộ nhớ, chiếm worker, lấp kho tệp hoặc tạo lượng dữ liệu vượt phạm vi tổ chức cho phép. Chỉ giới hạn số bản ghi ở giao diện không đủ: người gọi có thể sửa tham số, chọn nhiều cột, đưa một ô rất dài vào báo cáo hoặc gửi nhiều job đồng thời.

Bài học thuộc chương **Export Security** trong bảo mật logic nghiệp vụ. Mục tiêu là thiết kế giới hạn có thẩm quyền, kiểm tra khi dữ liệu thực sự được tạo và giữ đúng trạng thái, quota, quyền tải cùng kết quả khi vượt giới hạn.

Ví dụ xuyên suốt là xuất đề nghị mua hàng và lịch sử phê duyệt của một tenant.

## 1. Xác định đang giới hạn đại lượng nào

“Kích thước export” không phải một con số duy nhất.

| Đại lượng | Rủi ro cần kiểm soát |
|---|---|
| Số đối tượng nguồn | Query rộng, phạm vi nghiệp vụ quá lớn |
| Số dòng đầu ra | Join một-nhiều hoặc nhiều sheet làm số dòng tăng |
| Số cột và field | Mở rộng dữ liệu được lấy và chi phí tạo tệp |
| Độ dài một giá trị | Một ô hoặc tài liệu có thể chiếm nhiều bộ nhớ |
| Số byte được mã hóa | Kích thước artifact thực tế |
| Kích thước trước và sau nén | Tệp nhỏ khi truyền vẫn có thể chứa nội dung rất lớn |
| Tài nguyên trung gian | Buffer, tệp staging, dữ liệu workbook hoặc ảnh |
| Tổng nhiều phần, nhiều job | Chia nhỏ để né giới hạn hoặc lấp kho |
| Thời gian và số job đồng thời | Cạn worker, giữ snapshot hoặc kết nối quá lâu |

Không dùng số ký tự của chuỗi làm số byte của tệp. Encoding, dấu phân cách, escape, tiêu đề, footer và cấu trúc định dạng đều có thể tăng kích thước.

Nếu công bố một giới hạn bằng MB hoặc MiB, phải ghi đơn vị rõ và dùng nhất quán. Giá trị cấu hình, bộ đếm, quota và thông báo không nên hiểu các đơn vị khác nhau.

### 1.1. Số đơn không bằng số dòng báo cáo

Một đề nghị có nhiều quyết định có thể tạo nhiều dòng sau join. Giới hạn 1.000 đề nghị không tự giới hạn 1.000 dòng đầu ra.

Cần chọn đúng đại lượng cho từng giới hạn. Metadata cũng nên phân biệt sourceObjectCount, outputRowCount và outputBytes nếu chúng được sử dụng.

### 1.2. Giới hạn kích thước không thay thế quyền

Một tệp chỉ có một dòng vẫn có thể là dữ liệu tenant khác. Các predicate tenant, scope, visibility và projection phải được áp dụng trước khi lấy hoặc đếm dữ liệu.

Không chạy một phép count toàn cục rồi dùng tổng đó để báo lỗi kích thước cho caller không có quyền biết.

## 2. Giới hạn do máy chủ xác định

Một request có thể đề nghị số dòng tối đa, định dạng hoặc tập cột. Máy chủ phải tính giới hạn hiệu lực từ policy và quyền thực tế.

```text
Giới hạn hiệu lực:
    không vượt policy dataset
    không vượt phạm vi của actor và tenant
    không vượt giới hạn định dạng, hạ tầng
    không vượt quota còn được cấp
    chỉ nhận đề nghị client nếu nó nằm trong phạm vi hỗ trợ
```

Chỉ lấy min khi các số giới hạn cùng đại lượng và đơn vị. Không lấy min giữa số dòng với số byte hoặc giữa quota lưu trữ và giới hạn thời gian.

Những field như maxRows, unlimited, ignoreQuota hoặc adminMode không tự tạo quyền nâng giới hạn.

### 2.1. Phạm vi giới hạn cần được ghi vào job

Một kế hoạch xuất có thể lưu:

```text
tenant và actor có thẩm quyền
dataset, filter và projection hiệu lực
format và phiên bản quy tắc mã hóa
maxSourceObjects
maxOutputRows
maxEncodedBytes
maxCellSize hoặc các giới hạn giá trị
maxIntermediateStorage
quotaReservationRef
policyVersion
exceedBehavior
```

Các giá trị này được bảo vệ khỏi sửa tùy ý. Worker không lấy một giới hạn khác từ message chưa kiểm chứng.

Nếu policy đổi khi job đang chờ, phải định nghĩa cách giữ, thu hẹp hoặc đánh giá lại. Không tự chuyển giá trị thiếu thành vô hạn.

### 2.2. Không đổi định dạng để bỏ giới hạn

CSV, bảng tính, tài liệu hoặc archive có cách tiêu tốn tài nguyên khác nhau. Chọn một format khác không được bỏ quyền cột, quota hoặc giới hạn tổng.

Một tệp nén nhỏ không chứng minh nội dung khi giải nén hay xử lý nằm trong giới hạn. Cần đặt guard tại các tầng có ý nghĩa với pipeline thực tế.

Giới hạn tệp cuối không tự giới hạn mọi buffer hoặc tệp tạm mà một thư viện có thể tạo trước đó.

## 3. Ước lượng trước, kiểm tra thực tế khi sinh

Preflight hữu ích để từ chối sớm một yêu cầu rõ ràng quá lớn. Tuy nhiên, count và ước lượng có thể khác kết quả do dữ liệu thay đổi, join, độ dài ô hoặc cấu trúc định dạng.

Không coi một preflight dưới ngưỡng là quyền sinh dữ liệu không giới hạn.

Một luồng có thể là:

```text
xác thực và chốt scope
    → tính giới hạn từ policy
    → preflight trong phạm vi được phép nếu cần
    → nhận quota theo giao thức
    → sinh artifact riêng tư với bộ đếm thực tế
    → kiểm tra cả phần kết thúc định dạng
    → công bố nếu mọi điều kiện còn đạt
```

### 3.1. Kiểm tra số dòng trước khi nhận dòng vượt ngưỡng

Nếu giới hạn là N dòng, việc đọc thêm để biết còn dữ liệu phải được thực hiện có kiểm soát.

Khi xác định có dòng thứ N+1, áp dụng exceedBehavior. Không ghi nó rồi báo rằng tệp vẫn trong giới hạn N.

Một hàng nguồn chưa được phân quyền không được tính hoặc ghi như một hàng hợp lệ chỉ để hoàn thành vòng lặp.

### 3.2. Byte phải được đo ở vị trí phù hợp

Với giới hạn encoded bytes, bộ đếm phải nhìn các byte mà formatter thực sự đưa ra. Đếm độ dài field trước escape không đủ.

Cần tính cả header, dấu xuống dòng, tên sheet hoặc phần kết thúc mà format có thể phát sinh. Một tệp vượt ngưỡng trong lúc finalize cũng là vượt giới hạn.

Với pipeline nén, có thể cần nhiều bộ đếm: nội dung logic hoặc trung gian, byte trước nén và artifact sau nén. Không để một tầng nhỏ che việc tầng khác vượt policy.

### 3.3. Chặn trước những giá trị riêng lẻ quá lớn

Streaming nhiều dòng không bảo đảm không có một dòng cần cấp phát quá lớn. Giới hạn giá trị, số field, tài liệu đính kèm hoặc cấu trúc lồng nhau cần phù hợp.

Không truncate một field có ý nghĩa như số tiền, mã giao dịch hoặc căn cứ phê duyệt chỉ để vừa bộ nhớ. Thay đổi dữ liệu phải theo contract, không là cách chữa lỗi tài nguyên.

## 4. Chọn hành vi khi vượt giới hạn

| Hành vi | Điều cần bảo đảm |
|---|---|
| Từ chối toàn bản xuất | Không công bố tệp dở dang như kết quả đầy đủ |
| Trả một tập bị giới hạn | Contract nói rõ dữ liệu không đầy đủ và thứ tự chọn |
| Chia nhiều phần | Manifest, tổng dung lượng, quyền và quota bao phủ tất cả phần |
| Đề nghị thu hẹp filter | Không tự bỏ filter hoặc thay scope để có kết quả khác |

Trong ví dụ chính, vượt giới hạn làm job thất bại và không có artifact được phép tải.

### 4.1. Không cắt âm thầm

Nếu người dùng xin báo cáo đầy đủ, một tệp có N dòng đầu không được mang nhãn đã xuất hết.

Nếu sản phẩm cho phép limited export, cần metadata như limitReached hoặc completeness theo contract. Không tiết lộ tổng dữ liệu ngoài scope chỉ để mô tả phần thiếu.

### 4.2. Chia phần không làm mất giới hạn tổng

Mỗi phần dưới ngưỡng không bảo đảm tổng nhiều phần được phép. Cần giới hạn và nhận diện cùng một đơn vị xuất logic.

Cũng cần xét trường hợp nhiều job cùng lấy một phạm vi nhằm né quota. Phạm vi quota phải là phạm vi nghiệp vụ mà tổ chức thực sự muốn kiểm soát.

Nếu các phần được công bố dần, phải nói rõ kết quả có thể một phần. Không hứa tất cả cùng có hoặc cùng không nếu những phần trước đã tải được.

## 5. Quota trước cạnh tranh và khi có lỗi

Hai job có thể cùng thấy còn dung lượng rồi cùng vượt tổng. Một phép đọc quota trước khi tạo job không đủ nếu bước chiếm suất không nhất quán.

Có thể đặt reservation theo tenant, actor và loại tài nguyên với giao thức nguyên tử phù hợp.

Hai mô hình có thể dùng:

- Giữ trước một mức trần được cấp, rồi tất toán theo kết quả.
- Cấp dần trước khi ghi thêm, không cho vượt phần đã được cấp.

Nếu chỉ giữ theo ước lượng, khi dữ liệu lớn hơn dự kiến cần xin thêm hoặc dừng. Không coi ước lượng thấp là cách được phép vượt quota.

### 5.1. Phân biệt quota logic với dung lượng vật lý

Một job lỗi có thể chưa có kết quả công bố nhưng vẫn để lại tệp staging.

Nếu quota đo byte vật lý còn tồn tại, không hoàn toàn giải phóng phần đó trước khi đã xác nhận dọn hoặc chuyển nó sang một ngân sách staging được quản lý.

Nếu quota đo số lượt được chấp nhận, cách tính có thể khác. Cần đặt tên và hợp đồng rõ, không dùng một bộ đếm cho mọi mục đích.

### 5.2. Không để cleanup xóa nhầm

Tệp được gắn với tenant, job và attempt có thẩm quyền. Cleanup chỉ xử lý đúng đối tượng thuộc trạng thái được phép.

Sau lỗi công bố chưa rõ, cần đối soát xem artifact đã được tham chiếu hợp lệ hay chưa trước khi xóa.

Không dùng đường dẫn hoặc prefix do client gửi để dọn dung lượng.

## 6. Ví dụ Java: bộ đếm byte trên đường ghi thật

Đây là mã giả theo cú pháp Java. ByteSink và kiểu lỗi là các cổng của ứng dụng minh họa, không phải API của một thư viện định dạng cụ thể.

```java
final class BoundedByteSink {
    private final ByteSink delegate;
    private final long maximumBytes;
    private long completedBytes;

    BoundedByteSink(ByteSink delegate, long maximumBytes) {
        if (maximumBytes <= 0) {
            throw new InvalidExportPolicy("INVALID_BYTE_LIMIT");
        }
        this.delegate = Objects.requireNonNull(delegate);
        this.maximumBytes = maximumBytes;
    }

    void append(byte[] encodedChunk) {
        Objects.requireNonNull(encodedChunk);

        long remaining = maximumBytes - completedBytes;

        if (encodedChunk.length > remaining) {
            throw new ExportLimitExceeded("ENCODED_SIZE_LIMIT");
        }

        delegate.append(encodedChunk);
        completedBytes += encodedChunk.length;
    }

    long completedBytes() {
        return completedBytes;
    }
}
```

So sánh với phần còn lại giúp tránh phép cộng có thể tràn khi kiểm tra. Invariant của lớp là completedBytes không vượt maximumBytes trên các lần append đã hoàn tất.

Tuy nhiên, một lỗi ghi có thể xảy ra sau khi sink bên dưới đã nhận một phần byte. Bộ đếm trên không tự chứng minh kích thước vật lý chính xác của tệp lỗi. Cleanup và quota cần đối soát artifact staging theo giao thức.

### 6.1. Đặt guard đúng tầng

Formatter phải ghi mọi byte đầu ra qua guard, gồm tiêu đề và finalize. Không có đường ghi phụ bỏ qua sink.

Nếu format cần tệp trung gian trước khi tạo artifact, cần giới hạn cho phần trung gian riêng. Một wrapper ở bước upload cuối không bảo vệ bộ nhớ mà formatter đã dùng trước đó.

Nếu nén hoặc đóng gói, cần xác định guard nào đo trước nén, guard nào đo tệp cuối và giới hạn nào áp cho mỗi lớp.

### 6.2. Phối hợp số dòng và giá trị

Vòng sinh có thể làm:

```text
với từng row được phép:
    kiểm tra còn quyền nhận row mới theo maxOutputRows
    kiểm tra các giới hạn giá trị và projection
    mã hóa qua writer có guard
    ghi nhận row hoàn tất theo contract

finalize format qua cùng guard
xác nhận artifact hoàn chỉnh
kiểm tra trạng thái job, quyền và điều kiện công bố
công bố tham chiếu nếu tất cả đạt
```

Không lưu một trạng thái READY ngay khi ghi xong dòng cuối nếu footer hoặc bước đóng gói vẫn có thể thất bại.

Số dòng được ghi nhận cũng cần ngữ nghĩa rõ nếu writer lỗi giữa một row. Một count trong bộ nhớ không thay thế việc xác nhận artifact hoàn chỉnh.

## 7. Trạng thái, tác dụng và phản hồi khi vượt ngưỡng

Một vòng đời có thể phân biệt:

```text
QUEUED → RUNNING → READY
                 → LIMIT_EXCEEDED
                 → FAILED
                 → CANCELLED
```

Tên là ví dụ. Điều quan trọng là LIMIT_EXCEEDED không có đường tải như READY trong contract từ chối toàn tệp.

Một lỗi có thể trả mã an toàn như EXPORT_ROW_LIMIT hoặc EXPORT_BYTE_LIMIT, cùng gợi ý thu hẹp phạm vi được phép. Không trả nội dung hàng vừa làm vượt giới hạn nếu điều đó lặp dữ liệu nhạy cảm ngoài nhu cầu.

### 7.1. Không gửi trước rồi mới kiểm tra toàn tệp

Nếu response đã stream các byte tới client, việc phát hiện vượt giới hạn sau đó không thu hồi phần đã gửi.

Nếu yêu cầu là chỉ cấp một artifact hoàn chỉnh nằm trong giới hạn, cần staging riêng tư và cổng công bố phù hợp.

Nếu sản phẩm chọn streaming có thể ngắt, phải mô tả contract dữ liệu một phần và giới hạn ngay trên đường gửi. Nó không tương đương với từ chối toàn bản xuất trước khi công bố.

### 7.2. Byte limit không thay thế audit và phân quyền tải

Artifact READY vẫn cần đúng tenant, quyền tải, thời hạn và liên kết job.

Audit có thể lưu policyVersion, giới hạn được cấp, số đo hoàn tất, kết quả vượt giới hạn, job và attempt. Không ghi toàn bộ payload gây lỗi vào log.

Một lần retry job không được tự tăng trần. Một phương thức API hoặc key mới không tự cho bỏ giới hạn tổng.

## 8. Kiểm thử các cách vượt giới hạn

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Client tăng maxRows hoặc bật unlimited | Không vượt policy có thẩm quyền |
| Dữ liệu đúng bằng ngưỡng | Chấp nhận nếu mọi điều kiện khác và finalize đều đạt |
| Thêm một byte hoặc một row vượt ngưỡng | Hành vi đúng exceedBehavior, không công bố kết quả đầy đủ giả |
| Có ký tự nhiều byte | Đo byte mã hóa thực tế, không dùng số ký tự thay thế |
| Header hoặc footer làm vượt ngưỡng | Guard vẫn chặn, job không thành READY |
| Một cell rất lớn | Giới hạn tài nguyên phát huy trước cấp phát không kiểm soát |
| Join nhân số dòng | Output row limit vẫn đúng |
| Preflight thấp hơn dữ liệu thực tế | Guard runtime không bị bỏ qua |
| Nén tạo tệp nhỏ nhưng nội dung rất lớn | Các giới hạn nội dung và trung gian còn được giữ |
| Nhiều job cùng tranh quota | Không cùng tiêu phần tài nguyên không được cấp |
| Chia thành nhiều tệp hoặc job | Giới hạn tổng vẫn theo phạm vi đã định nghĩa |
| Sink lỗi sau ghi một phần | Không công bố tệp dở; quota và cleanup phản ánh dữ kiện biết được |
| Công bố thành công nhưng mất phản hồi | Không xóa artifact hợp lệ hoặc tạo thêm job sai contract |
| Job bị hủy trước công bố | Không đưa tệp vượt hoặc tệp cũ thành READY |
| Caller ngoài scope xin count để preflight | Không lộ số lượng hoặc metadata ngoài quyền |
| Policy hoặc quota source không xác định | Không coi giá trị thiếu là vô hạn |

### 8.1. Kiểm tra trạng thái sau lỗi

Cần đọc lại job, artifact, quota reservation, tham chiếu công bố và quyền tải. Chỉ assert có exception chưa chứng minh tệp không bị lộ.

Nếu còn staging riêng tư chờ dọn, kiểm tra nó không có đường tải thông thường và được tính tài nguyên đúng. Không yêu cầu báo đã xóa trong khi thực tế chưa xác nhận.

Thử cả lỗi tại finalize, upload, phép ghi công bố và mất phản hồi sau commit. Các điểm lỗi này có thể để lại tài nguyên khác nhau.

### 8.2. Kiểm thử tính nhất quán của contract

Với chế độ từ chối toàn tệp, không có artifact dở dang được cấp như một bản đầy đủ.

Với limited export, completeness và thứ tự chọn phải chính xác. Với chia phần, manifest cần chứa đúng phần được công bố và tổng không né quota.

Kiểm thử phải dùng dữ liệu có cardinality, độ dài và encoding đủ đa dạng. Một fixture chỉ có chuỗi ngắn và một dòng cho mỗi đối tượng không kiểm tra được các đường vượt giới hạn quan trọng.

## 9. Bài tập áp dụng

Thiết kế export đề nghị mua hàng có nhiều quyết định phê duyệt, hỗ trợ CSV và một định dạng đóng gói.

1. Xác định giới hạn theo đối tượng, dòng, byte, giá trị, trung gian và tổng quota.
2. Chọn nguồn policy và cách xử lý client xin vượt trần.
3. Phân biệt ước lượng với số đo runtime.
4. Đặt guard ở vị trí nhìn đủ header, nội dung, finalize và các lớp nén.
5. Định nghĩa exceedBehavior và trạng thái không được tải.
6. Vẽ reservation, tất toán, staging và cleanup khi có lỗi.
7. Viết ca hai job tranh quota, một cell lớn và footer vượt giới hạn.
8. Chỉ ra dữ kiện cần đối soát khi upload hoặc công bố có kết quả chưa rõ.

Một giới hạn có hiệu lực phải được đo và thực thi tại đúng tài nguyên mà nó bảo vệ. Policy, quota và vòng đời artifact cần phối hợp để một yêu cầu quá lớn không biến thành dữ liệu một phần bị công bố, tài nguyên không được tính hoặc quyền xuất rộng hơn được cấp.
