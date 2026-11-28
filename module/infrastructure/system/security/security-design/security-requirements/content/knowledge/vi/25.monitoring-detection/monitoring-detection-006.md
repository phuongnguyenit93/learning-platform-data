# Alert theo data export

## 1. Export hợp lệ vẫn có thể là tín hiệu rủi ro

Một nhân viên được phép xuất danh sách khách hàng để xử lý công việc. Trong một khoảng thời gian ngắn, tài khoản đó tạo nhiều báo cáo hơn bình thường, chọn phạm vi dữ liệu rộng và thực hiện ngay sau khi được cấp thêm quyền. Tất cả request đều vượt qua phân quyền, nhưng tổ hợp hành vi vẫn đáng để xem xét.

**Alert theo data export** là cảnh báo dựa trên các sự kiện và ngữ cảnh của việc tạo hoặc chuyển dữ liệu ra một định dạng, vị trí hay bên nhận xác định. Mục tiêu là phát hiện hành vi cần điều tra, không mặc định kết luận mọi export lớn là rò rỉ.

Trong chương Monitoring và detection, yêu cầu phải nối được rủi ro với nguồn telemetry, ngữ nghĩa phép đo, quy tắc đánh giá, người nhận cảnh báo và bằng chứng kiểm thử. Câu “cảnh báo khi export bất thường” chưa đủ để triển khai hoặc nghiệm thu.

Sau bài này, người học có thể:

- Xác định các giai đoạn export và điều mà mỗi tín hiệu thực sự chứng minh.
- Chọn ngưỡng theo khối lượng, tần suất, độ nhạy và ngữ cảnh.
- Đặc tả cửa sổ thời gian, dedup, dữ liệu đến muộn và thiếu telemetry.
- Thiết kế cảnh báo hữu ích mà không sao chép dữ liệu xuất hoặc secret.
- Liên kết yêu cầu phát hiện với kiến trúc, kiểm thử và quy trình phản ứng.

## 2. Xác định export nào nằm trong phạm vi

### 2.1. Không chỉ có nút Export trên giao diện

Các đường đi cần được xem xét có thể gồm:

| Đường đi | Tín hiệu có thể quan sát |
|---|---|
| Xuất CSV, bảng tính hoặc báo cáo | Yêu cầu, job, artifact và sự kiện tải |
| API lấy dữ liệu theo trang | Số request, phạm vi và lượng trả về theo hợp đồng |
| Job tích hợp theo lịch | Chủ thể dịch vụ, nguồn dữ liệu, đích và kết quả batch |
| Gửi báo cáo sang hệ thống khác | Lệnh gửi, đích đã phân loại và kết quả giao nhận |
| Tạo link tải có thời hạn | Việc cấp khả năng tải, tách biệt với việc đã tải |
| Tải object qua CDN hoặc kho lưu trữ | Sự kiện ở tầng phục vụ thực tế trong khả năng quan sát |
| Công cụ quản trị hoặc truy vấn dữ liệu | Audit của công cụ và phạm vi truy xuất được kiểm soát |

Không phải mọi đường đều dùng cùng một rule. Điều quan trọng là có danh mục và chủ sở hữu, tránh tuyên bố đã giám sát export trong khi chỉ quan sát một nút trên UI.

Nếu API phân trang có thể lấy toàn bộ tập dữ liệu, giới hạn một file export không bao phủ đường đó. Cần yêu cầu riêng hoặc ghi rõ đây là phần chưa được giám sát.

### 2.2. Phát hiện bổ sung cho phòng ngừa

Phân quyền, giới hạn phạm vi truy vấn, quota, phê duyệt và kiểm soát đích là những cơ chế phòng ngừa. Alert không thay thế chúng.

Một hành vi đã bị chặn vẫn có thể tạo tín hiệu đáng xem xét. Một hành vi được cho phép cũng vẫn có thể tạo cảnh báo. Cần phân biệt attempt, quyết định kiểm soát và kết quả thực tế.

Không dùng việc “sẽ có alert” làm lý do cho phép xuất dữ liệu vượt quyền. Cũng không tự biến mọi cảnh báo thành lệnh khóa tài khoản nếu policy chưa xác định hành động đó.

## 3. Phân biệt yêu cầu, tạo file và truyền dữ liệu

### 3.1. Các mốc có ý nghĩa khác nhau

```text
Export requested
  -> authorization và điều kiện bắt buộc
  -> job accepted
  -> artifact materialized
  -> download capability issued hoặc delivery requested
  -> delivery progress
  -> delivery completed / partial / failed
```

Tên sự kiện có thể khác theo hệ thống, nhưng hợp đồng phải làm rõ từng mốc.

| Mốc | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| Requested | Có yêu cầu export | Dữ liệu đã được tạo hoặc gửi |
| Job accepted | Hệ thống nhận công việc | Job đã hoàn tất |
| Artifact materialized | Có artifact theo phạm vi được ghi nhận | Người dùng đã tải hoặc đọc artifact |
| Link issued | Một khả năng tải đã được cấp | Link đã được sử dụng |
| Delivery progress | Tầng phục vụ báo lượng dữ liệu đã gửi theo phép đo | Người nhận đã đọc hoặc lưu mọi bản ghi |
| Delivery completed | Tầng nguồn xác nhận hoàn tất theo hợp đồng giao nhận | Có rò rỉ ra ngoài tổ chức hoặc chủ thể thực là người nào |

Nếu cảnh báo dựa trên artifact đã tạo, tiêu đề nên nói rõ “tạo nhiều dữ liệu xuất”, không ghi chắc chắn “đã tải toàn bộ dữ liệu”.

### 3.2. Lỗi không có nghĩa không có dữ liệu đi ra

Một download có thể gửi một phần nội dung rồi lỗi. Một dịch vụ gửi báo cáo có thể hoàn tất ở bên nhận nhưng timeout trước khi nhận phản hồi.

Giữ trạng thái partial hoặc unknown khi phù hợp. Không chỉ đếm HTTP response thành công rồi bỏ qua mọi đường lỗi, và không suy diễn rằng mỗi lỗi đều đã gửi đủ artifact.

Với link tải trực tiếp từ kho lưu trữ, ứng dụng có thể chỉ quan sát việc cấp link. Nếu chưa có sự kiện từ tầng tải, phải ghi giới hạn đó thay vì gán thành công của API cấp link thành dữ liệu đã truyền.

## 4. Chọn phép đo đúng trước khi chọn ngưỡng

### 4.1. Số hàng không phải số người, số byte không phải số hàng

| Phép đo | Định nghĩa cần chốt |
|---|---|
| Số export hoàn tất | Đếm sự kiện logic hoặc export ID nào, ở giai đoạn nào? |
| Số hàng materialized | Hàng kết quả tạo artifact hay thực thể nghiệp vụ duy nhất? |
| Kích thước artifact | Dung lượng định dạng nào, có nén hay không? |
| Byte truyền qua mạng | Byte thực gửi tại tầng nào, có tính retry và phần trùng không? |
| Độ rộng dữ liệu | Nhóm dữ liệu, phạm vi tenant, khoảng thời gian hoặc loại field nào? |
| Độ nhạy | Phân loại từ nguồn quản lý dữ liệu nào, ở revision nào? |

Một người có thể xuất hiện ở nhiều hàng. Nhiều export cũng có thể chứa các bản ghi trùng nhau. Không gọi tổng số hàng là số cá nhân duy nhất nếu chưa có cơ chế tính đúng thuộc tính đó.

Partial download không đủ để suy ra số hàng đã tới client bằng cách nhân tỷ lệ byte. Header, nén, cấu trúc định dạng và thứ tự bản ghi có thể làm suy luận đó sai.

### 4.2. Không cộng lẫn các giai đoạn

Không cộng `materializedRows` của job với cùng số hàng được ghi lại ở event tải để tính tổng export. Đó có thể là hai quan sát của một tập dữ liệu.

Mỗi rule cần ghi rõ đang đo việc chuẩn bị dữ liệu, việc cấp khả năng truy cập hay việc truyền dữ liệu. Có thể có các rule riêng liên kết cùng export ID.

Với range request, resume hoặc retry, cần phân biệt byte truyền trên đường mạng với phần nội dung logic không trùng. Nếu hệ thống chỉ có transport bytes, giữ tên và ngữ nghĩa đó; không đổi thành số byte duy nhất đã được lấy.

### 4.3. Số liệu phải đến từ nguồn tin cậy

Row count do client khai không nên là căn cứ duy nhất. Lấy kết quả từ job, bộ tạo artifact hoặc tầng phục vụ theo hợp đồng của chúng.

Kiểm tra giá trị âm, giới hạn kích thước, đơn vị và tràn số khi cộng. Dữ liệu không hợp lệ cần tạo tín hiệu chất lượng hoặc bị xử lý theo policy, không âm thầm thành số không để rule không kích hoạt.

## 5. Ngữ cảnh giúp phân biệt công việc bình thường và rủi ro

### 5.1. Chủ thể, phạm vi và vai trò

Xác định riêng người khởi tạo, principal thực thi job và phạm vi tenant. Nếu mọi job chạy dưới một service account rồi chỉ nhóm theo account đó, nhiều người có thể bị gộp thành một hành vi không thể điều tra.

Không lấy subject hoặc tenant thô từ header chưa xác minh. Với workload tự động, ghi rõ đó là chủ thể máy và quan hệ với lịch, policy hoặc bên yêu cầu.

Nhóm dữ liệu và hành động cũng quan trọng: một nhóm được phép xuất báo cáo tổng hợp không mặc nhiên có cùng hành vi bình thường với nhóm xử lý hồ sơ chi tiết.

### 5.2. Các tín hiệu có thể kết hợp

- Khối lượng hoặc tần suất cao trong một hay nhiều cửa sổ.
- Phạm vi dữ liệu rộng hơn công việc thường gặp của vai trò.
- Dữ liệu có độ nhạy cao, dù số lượng không lớn.
- Đích gửi mới, ngoài policy hoặc chưa đánh giá được.
- Export diễn ra gần một thay đổi quyền hoặc thay đổi phương thức truy cập.
- Nhiều yêu cầu nhỏ liên tiếp cùng chủ thể và nhóm dữ liệu.
- Job ngoài lịch hoặc khác phạm vi, đích và hạn mức đã đăng ký.

Mối liên hệ theo thời gian là tín hiệu, không tự chứng minh nguyên nhân. Một thay đổi quyền hợp lệ trước đợt xử lý dữ liệu lớn cũng có thể tạo cùng mẫu.

### 5.3. Đích gửi phải được phân loại mà không log khả năng truy cập

Nếu cần đánh giá destination, ưu tiên reference và trạng thái từ registry hoặc policy tin cậy. Không đưa nguyên URL có chữ ký, token hay thông tin xác thực vào event hoặc alert.

Đích được duyệt, đích ngoài policy và đích chưa xác định là ba trạng thái khác nhau. Không biến thiếu dữ liệu đánh giá thành “đã được duyệt”. Hành vi phòng ngừa khi chưa xác minh được đích là yêu cầu riêng của luồng.

## 6. Các lớp rule và lựa chọn ngưỡng

### 6.1. Ngưỡng tuyệt đối

Ví dụ một rule fixture:

> Trong cửa sổ trượt 15 phút, nếu một subject trong một tenant tạo artifact cùng nhóm dữ liệu đạt ít nhất 50.000 hàng hoặc ít nhất 8 export hoàn tất thì tạo candidate alert.

Các con số này chỉ phục vụ ví dụ và ca thử. Ngưỡng thật phải được chốt theo dữ liệu, vai trò, mục đích công việc và mức rủi ro của dự án.

Rule cần xác định dấu so sánh. `>= 50.000` khác `> 50.000`; kiểm thử phải có trường hợp dưới, đúng và trên biên.

### 6.2. Tần suất và nhiều cửa sổ

Một file nhỏ có thể không vượt ngưỡng khối lượng, nhưng nhiều file trong khoảng dài vẫn đáng chú ý. Có thể dùng các rule cho cửa sổ ngắn và dài với ngữ nghĩa rõ.

Không cộng kết quả của các cửa sổ chồng lấn rồi coi đó là tổng dữ liệu mới. Từng rule phải duy trì tập sự kiện và cách tính riêng phù hợp.

Rule chỉ dựa trên volume có thể bỏ sót một lượng nhỏ dữ liệu rất nhạy cảm. Phân loại dữ liệu hoặc thao tác ngoài policy có thể cần điều kiện riêng không phụ thuộc ngưỡng lớn.

### 6.3. Baseline theo nhóm và hành vi

Baseline có thể giúp nhận diện độ lệch so với vai trò, lịch hoặc chính chủ thể, nhưng cần dữ liệu đủ chất lượng và thời gian quan sát phù hợp.

Chủ thể mới, công việc mùa vụ hoặc thay đổi tổ chức có thể không có baseline đáng tin. Cần trạng thái cold start và phương án rule tĩnh hoặc rà soát bổ sung; không gán “không có baseline” thành “không bất thường”.

Không để những hành vi đang bị điều tra tự động trở thành chuẩn mới rồi làm mất cảnh báo. Việc cập nhật baseline cần có policy, revision và bằng chứng đánh giá.

### 6.4. Ngoại lệ có điều kiện

Một job được duyệt có thể có phạm vi dữ liệu, chủ thể, lịch, destination và ngân sách rõ. Ngoại lệ chỉ áp dụng khi các điều kiện đó khớp và còn hiệu lực.

Không allowlist toàn bộ service account, vai trò quản trị hoặc một tenant lớn vô thời hạn chỉ để giảm nhiễu. Đích đổi hoặc số lượng vượt phạm vi có thể cần được xem xét dù tên job vẫn như cũ.

Phân biệt sự kiện export vẫn được ghi với việc giảm notification. Suppression không nên xóa bằng chứng hoặc làm hoạt động biến mất khỏi đối soát.

## 7. Hợp đồng telemetry tối thiểu

### 7.1. Field và nguồn tạo giá trị

| Nhóm | Field minh họa | Nguồn |
|---|---|---|
| Hợp đồng | `schemaVersion`, `eventType` | Producer và registry schema |
| Định danh | `eventId`, `exportId`, `artifactRef` | Trạng thái export phía server |
| Chủ thể | `initiatorRef`, `executorRef`, `tenantRef` | Context xác thực và ủy quyền đã xác minh |
| Giai đoạn | `stage`, `outcome` | State machine export hoặc delivery |
| Dữ liệu | `datasetGroup`, `classification`, `catalogRevision` | Metadata được quản lý |
| Phép đo | `materializedRows`, `artifactBytes`, hoặc số liệu delivery riêng | Tầng tạo hoặc phục vụ thực tế |
| Đích | `destinationRef`, `destinationAssessment` nếu có | Registry và policy của luồng |
| Thời gian | `occurredAt`, thời điểm ingest riêng | Nguồn phát sinh và collector |
| Điều kiện | `approvalRef`, `scheduleRef`, `policyRevision` nếu áp dụng | Hồ sơ tin cậy, không do client tự khai |

Không nhất thiết mọi event đều có mọi field. Ví dụ mốc requested chưa biết số hàng thực tế; thiếu phép đo đó không được điền số không rồi khiến người đọc tưởng rằng kết quả đã được xác nhận.

### 7.2. Ví dụ event tạo artifact

```json
{
  "schemaVersion": 1,
  "eventType": "EXPORT_ARTIFACT_MATERIALIZED",
  "eventId": "ff80b022-4e62-47da-95b6-5db18ee544cb",
  "exportId": "abbc8ddc-933b-4f73-834b-979fe3dd52c6",
  "artifactRef": "artifact-fixture-61",
  "initiatorRef": "subject-fixture-17",
  "executorRef": "svc-report-worker",
  "tenantRef": "tenant-fixture-4",
  "datasetGroup": "CUSTOMER_PROFILE",
  "classification": "RESTRICTED",
  "materializedRows": 52000,
  "artifactBytes": 12400000,
  "outcome": "SUCCEEDED",
  "occurredAt": "2026-11-27T06:30:00Z",
  "policyRevision": "export-policy-r6"
}
```

Mọi giá trị là dữ liệu tổng hợp. Event chứng minh artifact đã được tạo theo hợp đồng, không chứng minh 52.000 hàng đã được tải hoặc dữ liệu đã bị đưa ra ngoài tổ chức.

Reference không được tự cấp quyền tải artifact. Không ghi nội dung bản ghi, danh sách email, token, cookie hoặc URL có chữ ký vào telemetry để phục vụ rule.

## 8. Cửa sổ thời gian, dedup và chất lượng dữ liệu

### 8.1. Event time khác ingest time

Rule cần chốt dùng thời điểm phát sinh hay thời điểm thu nhận. Nếu dùng event time, phải có policy cho độ trễ chấp nhận, sự kiện sai thời gian, thứ tự đến và việc cập nhật kết quả khi có dữ liệu muộn.

Một export lúc 09:00 nhưng event đến lúc 09:20 không tự trở thành hoạt động mới lúc 09:20. Replay lịch sử cũng cần chế độ xử lý rõ, tránh gửi notification hiện tại như thể sự việc vừa diễn ra.

Clock lệch hoặc timestamp do client tự khai có thể làm rule phân nhóm sai. Xác định nguồn tin cậy, giới hạn kiểm tra và tín hiệu chất lượng thay vì chỉ giả định mọi timestamp đều đúng.

### 8.2. Định danh sự kiện và export logic

Event ID giúp loại giao nhận trùng của cùng một sự kiện. Export ID giúp liên kết các mốc và tránh đếm một export nhiều lần trong cùng phép đo.

Không dedup mọi event có cùng export ID nếu chúng đại diện cho các giai đoạn hoặc lần tải khác nhau. Ngược lại, không đếm lại một artifact materialized chỉ vì exporter retry bằng cùng sự kiện.

Với event progress, phải chốt số liệu là delta hay tổng lũy kế. Cộng các tổng lũy kế như các delta có thể làm số byte tăng giả.

### 8.3. Không có dữ liệu không đồng nghĩa không có export

Phân biệt ít nhất:

- Dữ liệu đủ theo hợp đồng cho phạm vi và cửa sổ.
- Dữ liệu hợp lệ nhưng biết là còn thiếu; số đếm quan sát có thể là cận dưới.
- Dữ liệu không đáng tin về nội dung hoặc cách tổng hợp.

Nếu phần hợp lệ đã vượt ngưỡng, có thể tạo cảnh báo với ghi chú thiếu dữ liệu. Nếu số quan sát còn dưới ngưỡng nhưng nguồn bị thiếu, không nên kết luận chắc chắn không vượt ngưỡng.

Khi không còn tin số liệu do sai đơn vị, tràn số hoặc dedup hỏng, cần trạng thái chất lượng riêng. Không dùng một con số đã biết sai làm bằng chứng khẳng định mức export.

### 8.4. Phân tách tenant và chủ thể trong state

Aggregation key phải thể hiện phạm vi rule. Ví dụ subject, tenant và dataset group cần được tách rõ; không nhóm một subject reference không có namespace trên toàn bộ hệ thống nếu nó có thể trùng giữa tenant.

State của detector cũng là dữ liệu nhạy cảm về hành vi. Kiểm soát quyền, thời hạn và quy mô của nó; không chỉ bảo vệ kho event đầu vào.

## 9. Ví dụ Java: đánh giá rule volume với ba kết quả

Ví dụ dùng Java 17 trở lên và chỉ minh họa rule cho artifact đã tạo. Aggregator bên ngoài chịu trách nhiệm chọn đúng cửa sổ, scope và loại giao nhận trùng trước khi tạo summary.

```java
import java.util.Objects;

public final class ExportVolumeRule {
    private ExportVolumeRule() {}

    public enum SignalQuality {
        COMPLETE,
        PARTIAL_VALID,
        UNTRUSTWORTHY
    }

    public enum Decision {
        MATCHED,
        NOT_MATCHED,
        INSUFFICIENT_DATA
    }

    public record WindowSummary(
        long observedMaterializedRows,
        long distinctCompletedExports,
        SignalQuality quality
    ) {
        public WindowSummary {
            if (observedMaterializedRows < 0 || distinctCompletedExports < 0) {
                throw new IllegalArgumentException("NEGATIVE_MEASUREMENT");
            }
            Objects.requireNonNull(quality);
        }
    }

    public record Policy(long rowThreshold, long exportCountThreshold) {
        public Policy {
            if (rowThreshold <= 0 || exportCountThreshold <= 0) {
                throw new IllegalArgumentException("INVALID_THRESHOLD");
            }
        }
    }

    public static Decision evaluate(WindowSummary summary, Policy policy) {
        Objects.requireNonNull(summary);
        Objects.requireNonNull(policy);

        if (summary.quality() == SignalQuality.UNTRUSTWORTHY) {
            return Decision.INSUFFICIENT_DATA;
        }

        boolean thresholdReached =
            summary.observedMaterializedRows() >= policy.rowThreshold()
            || summary.distinctCompletedExports()
                >= policy.exportCountThreshold();

        if (thresholdReached) {
            return Decision.MATCHED;
        }
        if (summary.quality() == SignalQuality.PARTIAL_VALID) {
            return Decision.INSUFFICIENT_DATA;
        }
        return Decision.NOT_MATCHED;
    }
}
```

Các quyết định đáng chú ý:

- Chỉ dùng số hàng materialized và số export hoàn tất theo một ngữ nghĩa đã chốt.
- Ngưỡng là inclusive: đúng ngưỡng cũng MATCHED.
- Dữ liệu hợp lệ nhưng thiếu vẫn có thể chứng minh đã vượt ngưỡng nếu cận dưới đủ lớn.
- Dưới ngưỡng với dữ liệu thiếu không bị đồng nhất với NOT_MATCHED.
- Dữ liệu không đáng tin không được dùng để khẳng định volume đã vượt.

Kết quả INSUFFICIENT_DATA cần đi vào cơ chế theo dõi chất lượng thích hợp, không im lặng biến thành “an toàn”. Nếu có rủi ro độc lập từ một sự kiện đáng tin khác, detector khác vẫn có thể cảnh báo theo hợp đồng của nó.

Mẫu không triển khai baseline, event-time window, dedup, quyền đọc alert hoặc notification. Nó cũng không chứng minh summary đúng tenant, đúng chủ thể hay không tràn số trong quá trình tổng hợp. Những thuộc tính đó cần yêu cầu và kiểm thử riêng.

## 10. Từ rule matched tới cảnh báo có thể xử lý

### 10.1. Nội dung tối thiểu cho người trực

Một cảnh báo nên cho biết:

- Rule ID, revision, phạm vi và lý do khớp.
- Mốc quan sát: yêu cầu, tạo artifact hay delivery.
- Tenant, chủ thể tham chiếu và nhóm dữ liệu theo quyền nhận.
- Cửa sổ, số quan sát, đơn vị và ngưỡng áp dụng.
- Chất lượng dữ liệu, phần chưa biết và độ trễ nếu có.
- Event hoặc export reference để truy vết trong công cụ được phân quyền.
- Chủ sở hữu xử lý, mức ưu tiên và runbook tương ứng.

Không đính kèm file export, các hàng mẫu chứa PII hoặc link tải có token. Nội dung gửi tới kênh thông báo cũng là một lần phát hành dữ liệu mới và cần mức chi tiết phù hợp.

### 10.2. Dedup notification không làm mất sự kiện mới

Một rule có thể tiếp tục khớp ở mỗi lần cập nhật cửa sổ. Cần định nghĩa cách nhóm thành một alert hoặc incident, khoảng nhắc lại và điều kiện tăng mức ưu tiên.

Nếu xuất hiện dữ liệu nhạy hơn, đích khác hoặc volume tăng đáng kể, suppression cũ không nên tự che mọi diễn biến mới. Giữ lịch sử cập nhật và bằng chứng dù không gửi một notification riêng cho từng event.

Retry gửi cảnh báo cần định danh ổn định để bên nhận hoặc hệ thống quản lý incident tránh tạo nhiều bản cho cùng một lần phát hành logic. Không tuyên bố exactly once chỉ vì có một UUID.

### 10.3. Giao nhận và phân quyền

Xác định ai nhận alert của tenant hoặc hệ thống nào. Người trực cần quyền truy cập bằng chứng phù hợp, không phải một URL bypass quyền.

Khi notification thất bại, có retry, trạng thái chưa giao và tín hiệu vận hành theo hợp đồng. Không coi “rule matched” là đã có người nhận hay đã xác nhận xử lý.

## 11. Triage và phản ứng theo mức bằng chứng

Một runbook có thể hướng dẫn:

1. Xác minh nguồn, ngữ nghĩa phép đo và việc loại trùng.
2. Đối chiếu chủ thể khởi tạo với executor của job.
3. Kiểm tra mục đích công việc, lịch và ngoại lệ còn hiệu lực.
4. Xem phân loại dữ liệu, phạm vi quyền và destination assessment.
5. Phân biệt artifact đã tạo, khả năng tải đã cấp và lượng delivery đã quan sát.
6. Liên kết với thay đổi quyền, xác thực hoặc tín hiệu khác trong phạm vi được phép.
7. Quyết định hành động theo policy cùng mức tin cậy của bằng chứng.
8. Ghi kết quả điều tra, giới hạn và lý do đóng hoặc chuyển cấp.

Hành động có thể là yêu cầu xác minh công việc, tạm giữ một job, hạn chế link tải hoặc chuyển sang quy trình ứng phó. Chọn hành động phụ thuộc quyền, kiến trúc và rủi ro của sản phẩm.

Không tự động khóa toàn bộ tài khoản chỉ vì một lần export vượt baseline nếu chưa có chính sách và kiểm chứng cho phản ứng đó. Phản ứng sai có thể gián đoạn công việc hợp lệ hoặc tạo đường gây từ chối dịch vụ.

Thu hồi link sau khi đã tải không thu hồi bản sao mà người nhận đã có. Xóa artifact cũng không chứng minh dữ liệu chưa từng được truyền. Runbook phải mô tả đúng giới hạn của từng biện pháp.

## 12. Bộ yêu cầu bảo mật có thể nghiệm thu

Các mã sau là mẫu cho dự án, không phải kết quả chứng minh của một hệ thống cụ thể.

| ID | Yêu cầu | Bằng chứng |
|---|---|---|
| EXP-DET-01 | Danh mục đường export, tầng phục vụ và chủ sở hữu được xác định | Inventory và sơ đồ dữ liệu |
| EXP-DET-02 | Event phân biệt request, artifact, capability và delivery cùng kết quả partial hoặc unknown | State machine, schema và fixture |
| EXP-DET-03 | Phép đo, đơn vị, nguồn và aggregation key được chốt cho từng rule | Hợp đồng summary và mapping field |
| EXP-DET-04 | Ngưỡng, cửa sổ, dấu so sánh, độ nhạy và ngoại lệ có revision | Rule registry và ca biên |
| EXP-DET-05 | Giao nhận trùng, các giai đoạn và progress không bị cộng sai | Thử retry, delta và tổng lũy kế |
| EXP-DET-06 | Dữ liệu muộn, replay, clock bất thường và thiếu telemetry có hành vi rõ | Fixture event time và chất lượng nguồn |
| EXP-DET-07 | Baseline thiếu hoặc không đáng tin không tự trở thành kết luận không bất thường | Ca cold start và thay đổi nhóm |
| EXP-DET-08 | Ngoại lệ khớp chủ thể, phạm vi, đích, thời gian và ngân sách đã chốt | Thử ngoại lệ hết hạn hoặc sai điều kiện |
| EXP-DET-09 | Event, state và alert không chứa payload export, credential hoặc link cấp quyền | Canary và kiểm tra các sink |
| EXP-DET-10 | Rule matched tạo alert có bằng chứng, chất lượng dữ liệu và chủ sở hữu; notification có trạng thái giao nhận | Thử nội dung, routing và lỗi kênh gửi |
| EXP-DET-11 | Tìm kiếm, điều tra và export bằng chứng đúng tenant và vai trò | Ma trận quyền và ca truy cập chéo |
| EXP-DET-12 | Phản ứng tự động, nếu có, là policy riêng có điều kiện và khả năng kiểm chứng | Ca phản ứng đúng, sai và phục hồi |
| EXP-DET-13 | Khoảng trống telemetry, backlog và rule lỗi có tín hiệu vận hành | Fault injection và hồ sơ quan sát |
| EXP-DET-14 | Nghiệm thu gắn với build, rule revision, catalog dữ liệu, inventory và giới hạn bao phủ | Hồ sơ kết quả và phần còn thiếu |

### 12.1. Đặc tả sâu hơn cho một rule volume

```text
Mục đích:
  Phát hiện subject tạo lượng artifact lớn trong một tenant và nhóm dữ liệu.

Nguồn:
  Event materialized từ producer tin cậy, không dùng row count do client khai.

Tổng hợp:
  Cửa sổ và aggregation key theo revision rule.
  Loại giao nhận trùng và chỉ tính đúng giai đoạn đã chọn.

Quyết định:
  MATCHED khi phép đo tin cậy đạt ngưỡng inclusive.
  NOT_MATCHED chỉ trong phạm vi dữ liệu đủ theo hợp đồng.
  INSUFFICIENT_DATA khi chưa có căn cứ kết luận dưới ngưỡng.

Alert:
  Nêu rõ đây là artifact đã tạo, chưa khẳng định download hoàn tất.
  Có ngưỡng, đơn vị, thời gian, chất lượng và reference điều tra an toàn.

Nghiệm thu:
  Ca biên, retry, dữ liệu muộn, thiếu nguồn và kênh gửi lỗi đều được kích hoạt.
```

Một rule phát hiện delivery cần hợp đồng riêng với phép đo từ tầng phục vụ. Không thay tên field rồi tái sử dụng mọi kết luận của rule materialized.

## 13. Kiểm thử bằng sự kiện và artifact tổng hợp

### 13.1. Ma trận kiểm thử minh họa

| Ca | Điều kiện kích hoạt | Điều kiện đạt |
|---|---|---|
| TC-EXP-01 | Artifact đạt ngưỡng volume | Có alert đúng rule, nêu materialized, không khẳng định đã tải |
| TC-EXP-02 | Volume dưới ngưỡng và nguồn đủ | Không khớp rule đó; không bị hiểu là mọi rủi ro khác đã loại trừ |
| TC-EXP-03 | Các giá trị dưới, đúng và trên biên | Dấu so sánh và đơn vị đúng hợp đồng |
| TC-EXP-04 | Nhiều export nhỏ cùng scope trong cửa sổ | Tổng hợp đúng, không chỉ kiểm tra từng file riêng |
| TC-EXP-05 | Giao lại event, nhiều stage và progress lũy kế | Không cộng trùng hoặc cộng tổng lũy kế như delta |
| TC-EXP-06 | Event muộn, đảo thứ tự và replay lịch sử | Cửa sổ, cập nhật và chế độ notification đúng policy |
| TC-EXP-07 | Mất telemetry hoặc summary không đáng tin | Có trạng thái chất lượng, không kết luận an toàn giả |
| TC-EXP-08 | Nhiều initiator dùng cùng worker | Không gộp nhầm mọi hoạt động thành một người hoặc tenant |
| TC-EXP-09 | Job theo lịch có ngoại lệ, sau đó đổi đích hoặc vượt phạm vi | Ngoại lệ chỉ áp dụng khi đủ điều kiện |
| TC-EXP-10 | Chỉ cấp link nhưng chưa có download | Không gán lượng artifact thành dữ liệu đã truyền |
| TC-EXP-11 | Partial, range, resume hoặc timeout sau giao nhận | Phép đo giữ đúng nghĩa, không suy số hàng nhận từ tỷ lệ byte |
| TC-EXP-12 | Export qua API hoặc đường ngoài UI trong inventory | Đường đó có tín hiệu và rule phù hợp, hoặc giới hạn được ghi rõ |
| TC-EXP-13 | Canary trong payload, signed URL hoặc error upstream | Event và alert không phát hành dữ liệu bị cấm |
| TC-EXP-14 | Vai trò sai hoặc tenant khác đọc alert và evidence | Không nhận dữ liệu ngoài phạm vi quyền |
| TC-EXP-15 | Notification lỗi, retry và suppression | Có trạng thái giao nhận; tránh bản trùng nhưng không che diễn biến cần chuyển cấp |
| TC-EXP-16 | Chủ thể mới, baseline đổi hoặc rule revision mới | Cold start và thay đổi policy có kết quả theo hợp đồng, không mặc định bình thường |

### 13.2. Chứng minh đúng nhánh đã chạy

Nếu chỉ tạo một file thử mà không kích hoạt event producer hoặc pipeline, chưa kiểm chứng rule thực tế. Nếu notification không tới vì routing sai, việc thấy MATCHED trong bộ nhớ chưa chứng minh cảnh báo đã được giao.

Ca dedup phải giữ nguyên định danh của cùng sự kiện; ca hai export độc lập phải có định danh khác để tránh chứng minh một bộ lọc đã bỏ cả dữ liệu hợp lệ.

Với ca missing telemetry, xác nhận nguồn thực sự không đủ theo hợp đồng. Với partial valid, cần biết phần đã quan sát không bị đếm sai thì mới gọi nó là cận dưới.

### 13.3. Không cần dữ liệu thật để chứng minh rule

Dùng tenant, chủ thể, artifact và destination tổng hợp. Không cần xuất hồ sơ thật hoặc đưa link production vào kênh alert để kiểm tra chống lộ.

Fixture phải ghi rõ volume, stage, event time, delivery time và điều kiện ngoại lệ. Giá trị trong fixture chỉ phục vụ tính tái hiện, không tự trở thành ngưỡng vận hành.

## 14. Đo hiệu quả và vận hành detector

### 14.1. Độ trễ cần được tách thành các đoạn

Xác định mốc bắt đầu đo: lúc hành vi xảy ra, lúc producer phát event, lúc detector có đủ bằng chứng hay lúc rule khớp. Độ trễ notification là một đoạn khác với độ trễ nguồn.

Một cửa sổ dài không nhất thiết đòi chờ hết cửa sổ mới cảnh báo nếu cận dưới hợp lệ đã đạt ngưỡng. Ngược lại, không cam kết độ trễ từ hành vi nếu không kiểm soát được thời gian phát và giao telemetry.

Đặc tả giới hạn, điều kiện nguồn và cách đo theo dự án. Không dùng một con số “real time” thiếu mốc thời gian làm tiêu chí nghiệm thu.

### 14.2. Chất lượng cảnh báo và bao phủ

Theo dõi các alert có ích, nhiễu do công việc hợp lệ, rule thường xuyên thiếu dữ liệu, đường export chưa có tín hiệu và incident được xác nhận nhưng rule không phát hiện.

Tỷ lệ false positive hoặc khả năng phát hiện chỉ có ý nghĩa khi biết tập đánh giá và chất lượng nhãn. Không suy một bộ replay nhỏ đại diện cho mọi hành vi tấn công hoặc mọi mùa hoạt động.

Điều chỉnh rule cần revision, lý do và bộ thử hồi quy. Không chỉ tăng ngưỡng đến khi hết alert mà bỏ qua các kịch bản rủi ro cần phát hiện.

### 14.3. Quan sát pipeline mà không tăng rủi ro dữ liệu

Metric có thể dùng rule ID, nhóm lỗi, mức ưu tiên hoặc trạng thái giao nhận với tập giá trị được quản lý. Không dùng token, artifact URL, subject ID hoặc event ID làm label cho mỗi chuỗi thời gian.

Kiểm soát retention cho event, state cửa sổ, alert và bản export điều tra. Retry hoặc restore không nên vô tình biến lịch sử thành dữ liệu giữ vô hạn hoặc cảnh báo mới.

Các thay đổi về route, catalog, exporter, CDN, chính sách quyền và công việc theo lịch có thể thay giả định của rule. Xem xét lại inventory và bằng chứng liên quan khi những thay đổi đó xảy ra.

## 15. Truy vết rủi ro tới bằng chứng nghiệm thu

Một chuỗi minh họa:

```text
Rủi ro:
  Một subject lấy dữ liệu qua nhiều export nhỏ để không vượt giới hạn từng file.
    -> EXP-DET-01, EXP-DET-03, EXP-DET-04, EXP-DET-05
    -> telemetry cùng scope và cửa sổ tổng hợp đúng nghĩa
    -> TC-EXP-03, TC-EXP-04, TC-EXP-05, TC-EXP-08
    -> event logic, summary, rule decision và alert được giao
    -> kết luận theo inventory, rule revision và fixture đã kiểm tra
```

Hồ sơ nghiệm thu cần ghi build, nguồn telemetry, schema, rule revision, catalog dữ liệu, phạm vi tenant, fixture, kết quả và giới hạn quan sát.

Một tiêu chí đo được có thể là:

> Trên các đường export và rule đã liệt kê, mọi ca bắt buộc được kích hoạt đúng nhánh; phép đo và cửa sổ đúng hợp đồng; các tình huống rủi ro được chỉ định tạo alert có reference điều tra an toàn; dữ liệu thiếu không bị báo là bình thường; notification và quyền đọc đạt policy. Phần chưa có bằng chứng được ghi riêng, không tính là PASS.

Điều này không khẳng định mọi export bất thường đều là rò rỉ hoặc mọi hành vi lấy dữ liệu đều đã được phát hiện. Giới hạn của kết luận phải đi cùng inventory, ngữ nghĩa tín hiệu và mô hình rủi ro.

## 16. Thực hành đặc tả cho nền tảng chăm sóc khách hàng

Một nền tảng có export CSV, API phân trang và job đồng bộ theo lịch. Nhân sự hỗ trợ có thể tạo báo cáo theo tenant; worker dùng chung một service account. File được lưu ở object storage và người dùng tải bằng link có thời hạn. Hiện tại hệ thống chỉ cảnh báo khi một request export khai báo hơn một ngưỡng row count do client gửi.

Hãy xây dựng một đặc tả gồm:

1. Inventory các đường lấy dữ liệu và tầng có thể quan sát từng đường.
2. State machine phân biệt request, materialized, link issued và delivery.
3. Nguồn tin cậy cho row count, kích thước artifact và số liệu truyền.
4. Aggregation key phân biệt initiator, executor, tenant và nhóm dữ liệu.
5. Rule volume, tần suất hoặc độ nhạy cùng cửa sổ và dấu so sánh rõ ràng.
6. Policy cho baseline thiếu, event muộn, retry, replay và telemetry không đủ.
7. Ngoại lệ có hạn cho job theo lịch, ràng buộc phạm vi và destination.
8. Alert không chứa dữ liệu xuất, token hoặc signed URL, có chủ sở hữu và runbook.
9. Ma trận thử nhiều export nhỏ, link chưa dùng, partial download và notification lỗi.
10. Tiêu chí nghiệm thu liên kết rủi ro, kiến trúc, rule revision và bằng chứng.

Hồ sơ hoàn thành cần cho người khác hiểu chính xác detector đã thấy điều gì, chưa biết điều gì, vì sao cần cảnh báo và người có quyền sẽ kiểm chứng tiếp ở đâu mà không làm dữ liệu nhạy cảm lan rộng qua hệ thống giám sát.
