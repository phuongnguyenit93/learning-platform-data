# Chế độ xem trước, xác nhận và ghi nhận tác vụ có ảnh hưởng lớn

Command có thể xóa dữ liệu, thu hồi quyền, triển khai phiên bản, đóng tài khoản hoặc thay đổi cấu hình của cả hệ thống. Với những thao tác như vậy, chỉ kiểm tra cú pháp và gọi service ngay khi người dùng nhấn Enter là chưa đủ. Người dùng cần thấy trước phạm vi ảnh hưởng, có cơ hội xác nhận rõ ràng và hệ thống cần lưu lại bằng chứng về quyết định cùng kết quả thực thi.

Spring Shell cung cấp các thành phần tương tác như ConfirmationInput và ComponentFlow để xây dựng bước xác nhận trong phiên shell. Tuy nhiên, chế độ xem trước, quy tắc phê duyệt, tính an toàn của thao tác và audit trail là trách nhiệm của ứng dụng. Bài học này trình bày cách kết hợp các phần đó thành một quy trình có thể kiểm soát, kiểm thử và truy vết.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Thiết kế command có chế độ xem trước mà không làm thay đổi dữ liệu.
- Phân biệt preview, dry-run, confirmation và execution.
- Dùng ConfirmationInput hoặc ComponentFlow để hỏi xác nhận trong phiên tương tác.
- Chọn cách xác nhận tường minh cho command chạy bằng script hoặc automation.
- Thiết kế thông tin preview để người dùng hiểu chính xác đối tượng và tác động.
- Kiểm tra lại trạng thái, quyền và dữ liệu ngay trước khi thực thi.
- Ghi audit event cho preview, từ chối, hủy, bắt đầu, thành công và thất bại.
- Phân biệt audit trail với log kỹ thuật thông thường.
- Bảo vệ thao tác khỏi chạy lặp, dữ liệu thay đổi giữa preview và execution, và việc ghi nhận thiếu nhất quán.
- Kiểm thử cả nhánh xác nhận, hủy, dry-run, non-interactive và lỗi thực thi.

## 1. Vì sao tác vụ có ảnh hưởng lớn cần quy trình riêng?

Một lệnh như liệt kê khách hàng thường chỉ đọc dữ liệu. Nếu người dùng nhập sai bộ lọc, hậu quả chủ yếu là nhận kết quả không mong muốn. Ngược lại, một lệnh xóa hàng nghìn bản ghi hoặc triển khai lên production có thể gây tác động khó đảo ngược.

Ví dụ:

~~~text
storage purge --bucket customer-archive --older-than-days 365
account disable --account-id A-1042
deployment apply --environment production --version 2026.11.26
access revoke --role billing-admin --user user-42
~~~

Trước khi thực hiện những lệnh này, người dùng cần biết:

- Đối tượng nào sẽ bị tác động.
- Phạm vi và số lượng bản ghi hoặc tài nguyên liên quan.
- Môi trường hoặc tenant đích.
- Hành động có thể đảo ngược hay không.
- Điều kiện nào có thể làm kết quả khác với dự kiến.
- Hệ thống sẽ làm gì nếu một phần thao tác thất bại.

Một quy trình an toàn thường có bốn giai đoạn:

1. **Preview:** tính toán và trình bày tác động dự kiến.
2. **Confirmation:** yêu cầu người dùng xác nhận đúng hành động và phạm vi đó.
3. **Execution:** kiểm tra lại điều kiện rồi thực hiện thay đổi.
4. **Audit:** ghi nhận ai đã yêu cầu, ai xác nhận, điều gì đã xảy ra và kết quả cuối cùng.

~~~mermaid
flowchart TD
    A[Nhận command và kiểm tra input] --> B[Kiểm tra danh tính và quyền]
    B --> C[Tạo preview chỉ đọc]
    C --> D[Hiển thị đối tượng và tác động]
    D --> E{Chỉ xem trước?}
    E -->|Có| F[Ghi nhận preview]
    F --> G[Kết thúc, không thay đổi dữ liệu]
    E -->|Không| H{Có xác nhận hợp lệ?}
    H -->|Không| I[Ghi nhận hủy hoặc từ chối]
    I --> J[Kết thúc, không thực hiện]
    H -->|Có| K[Kiểm tra lại trạng thái và quyền]
    K --> L[Thực hiện trong transaction hoặc cơ chế an toàn]
    L --> M[Ghi audit kết quả]
    M --> N[Trả kết quả cho người dùng]
~~~

Các giai đoạn này có thể được triển khai ở nhiều lớp. Spring Shell nhận input và điều khiển trải nghiệm command; service/domain layer chịu trách nhiệm kiểm tra và thực hiện hành động; audit service ghi nhận sự kiện.

## 2. Phân biệt preview, dry-run, confirmation và execution

Các thuật ngữ này thường được dùng gần nhau nhưng có ý nghĩa khác nhau:

| Khái niệm | Mục đích | Có thay đổi dữ liệu nghiệp vụ không? |
|---|---|---|
| Preview | Cho biết điều gì dự kiến xảy ra | Không |
| Dry-run | Chạy quy trình tính toán/kiểm tra mà không commit thay đổi | Không, nếu được thiết kế đúng |
| Confirmation | Ghi nhận người dùng đồng ý với hành động và phạm vi đã trình bày | Không |
| Execution | Thực hiện hành động thật | Có thể |
| Audit | Lưu dấu vết về yêu cầu, quyết định và kết quả | Ghi dữ liệu audit, không thay đổi dữ liệu nghiệp vụ mục tiêu |

Spring Shell không tự động cung cấp một cờ dry-run chung cho mọi command. Ứng dụng tự khai báo option như --dry-run và bảo đảm nhánh đó không gọi thao tác ghi dữ liệu. Tương tự, việc hiển thị một prompt xác nhận không tự bảo đảm service chỉ thực hiện đúng nội dung đã được preview.

Một dry-run đúng nghĩa không chỉ bỏ qua câu lệnh cuối cùng. Nó cần tránh mọi tác dụng phụ trong toàn bộ luồng, chẳng hạn:

- Không xóa, cập nhật hoặc tạo bản ghi nghiệp vụ.
- Không gửi email hoặc thông báo thật.
- Không phát lệnh tới hệ thống triển khai.
- Không tiêu thụ tài nguyên hoặc quota theo cách không thể hoàn tác.
- Không tạo reservation hoặc khóa tài nguyên mà không có quy tắc giải phóng rõ ràng.

Có thể vẫn ghi audit event cho việc preview đã được yêu cầu. Event đó phải được phân biệt với event thực thi thành công để báo cáo không nhầm dry-run thành thay đổi thật.

## 3. Thiết kế preview chỉ đọc

Preview cần được tạo từ cùng quy tắc lọc và cùng điều kiện nghiệp vụ với thao tác thực tế. Nếu preview đếm bản ghi theo một bộ lọc nhưng execution dùng bộ lọc khác, người dùng có thể xác nhận một tác động trong khi hệ thống thực hiện tác động khác.

Một preview hữu ích nên thể hiện:

| Thông tin | Ví dụ |
|---|---|
| Hành động | Xóa bản lưu trữ cũ |
| Đối tượng đích | Bucket customer-archive |
| Môi trường | production |
| Phạm vi | 2.480 object |
| Dung lượng dự kiến | 18,6 GB |
| Điều kiện lọc | Object cũ hơn 365 ngày |
| Tác động | Không thể khôi phục sau khi retention window kết thúc |
| Snapshot/version | storage revision 8f3a... |
| Thời điểm tính toán | 2026-11-26T14:20:00Z |

Thông tin snapshot hoặc version giúp phát hiện dữ liệu thay đổi giữa preview và execution. Nếu nguồn dữ liệu không hỗ trợ version, service cần tính lại điều kiện và so sánh tác động trước khi commit.

Ví dụ model:

~~~java
public record PurgePreview(
        String bucket,
        int affectedObjects,
        long estimatedBytes,
        String filterDescription,
        String snapshotVersion,
        Instant calculatedAt,
        boolean irreversible) {
}
~~~

Service chỉ tạo preview:

~~~java
public PurgePreview previewPurge(String bucket, int olderThanDays) {
    Instant cutoff = clock.instant().minus(olderThanDays, ChronoUnit.DAYS);
    PurgeSelection selection = repository.findPurgeCandidates(bucket, cutoff);

    return new PurgePreview(
            bucket,
            selection.count(),
            selection.totalBytes(),
            "created before " + cutoff,
            selection.snapshotVersion(),
            clock.instant(),
            true);
}
~~~

Đây là ví dụ minh họa. Repository phải thực hiện truy vấn chỉ đọc; không xóa, đánh dấu, chuyển trạng thái hoặc đặt chỗ tài nguyên trong phương thức preview.

### 3.1. Preview không phải khóa dữ liệu

Preview phản ánh trạng thái tại một thời điểm. Sau khi hiển thị, bản ghi mới có thể được tạo, quyền có thể bị thu hồi hoặc điều kiện lọc có thể thay đổi. Không coi preview như một reservation hoặc bảo đảm rằng execution sẽ có đúng số lượng đã hiển thị.

Một cách an toàn là gắn preview với snapshot version, revision hoặc token có thời hạn. Khi người dùng xác nhận, service:

1. Đọc lại trạng thái hiện tại.
2. Xác nhận actor vẫn có quyền.
3. Kiểm tra version/snapshot còn phù hợp.
4. Tính lại phạm vi tác động nếu cần.
5. Từ chối và yêu cầu preview mới nếu phạm vi đã thay đổi đáng kể.

Với thao tác có thể gây hậu quả lớn, không tự động mở rộng phạm vi sau khi người dùng xác nhận. Nếu preview hiển thị 100 tài nguyên nhưng execution hiện tìm thấy 140 tài nguyên, hãy dừng và yêu cầu xác nhận lại.

## 4. Trình bày preview để người dùng xác nhận đúng

Không chỉ hiển thị một câu chung chung như “Bạn có chắc không?”. Prompt cần gắn với thông tin người dùng vừa xem:

~~~text
KẾ HOẠCH XÓA LƯU TRỮ

Môi trường:       production
Bucket:           customer-archive
Điều kiện:        cũ hơn 365 ngày
Số object:        2.480
Dung lượng:       18,6 GB
Khả năng khôi phục: Không có sau khi xóa

Hành động này sẽ xóa vĩnh viễn các object trong phạm vi trên.
Tiếp tục? [y/N]
~~~

Thông tin quan trọng nên nằm gần câu hỏi xác nhận để người dùng không phải nhớ một bản preview đã hiển thị từ lâu. Với thao tác có nhiều bước, hãy tóm tắt lại đối tượng và tác động ngay trước bước cuối.

Đối với thao tác rủi ro rất cao, câu trả lời yes/no có thể chưa đủ. Có thể yêu cầu người dùng nhập lại tên môi trường hoặc một cụm xác nhận cụ thể, ví dụ:

~~~text
Để tiếp tục, nhập chính xác: DELETE customer-archive
~~~

Typed confirmation giúp giảm thao tác nhầm, nhưng vẫn không phải authorization. Người dùng nhập đúng cụm từ vẫn phải có quyền thực hiện hành động.

## 5. Hỏi xác nhận trong Spring Shell 3.4

Spring Shell 3.4 có ConfirmationInput, một component hỏi câu trả lời yes/no. Component nhận terminal, nội dung câu hỏi và giá trị mặc định. Tài liệu dùng giá trị mặc định false để người dùng phải chủ động chọn Yes thay vì vô tình chấp nhận bằng cách nhấn Enter.

Ví dụ dưới đây dùng mô hình annotation legacy để minh họa component tương tác:

~~~java
import org.springframework.shell.component.ConfirmationInput;
import org.springframework.shell.component.ConfirmationInput.ConfirmationInputContext;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;

@ShellComponent
public class StorageCommands extends AbstractShellComponent {

    public boolean confirmPurge(PurgePreview preview) {
        String question = "Delete " + preview.affectedObjects()
                + " objects from " + preview.bucket() + "?";

        ConfirmationInput component =
                new ConfirmationInput(getTerminal(), question, false);
        component.setResourceLoader(getResourceLoader());
        component.setTemplateExecutor(getTemplateExecutor());

        ConfirmationInputContext context =
                component.run(ConfirmationInputContext.empty());

        return Boolean.TRUE.equals(context.getResultValue());
    }
}
~~~

Giá trị false ở constructor là lựa chọn mặc định. Nếu người dùng chỉ nhấn Enter, component không xác nhận hành động. Kết quả được đọc qua getResultValue().

Tài liệu chính thức: [Confirmation component — Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/components/ui/confirmation.html) và [ConfirmationInput API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/ConfirmationInput.html).

### 5.1. Chỉ hỏi sau khi đã hiển thị preview

Thứ tự nên là:

1. Tạo preview.
2. In toàn bộ thông tin tác động.
3. Đặt câu hỏi xác nhận có nhắc lại đối tượng và phạm vi.
4. Nếu người dùng từ chối, kết thúc mà không gọi service thay đổi dữ liệu.
5. Nếu người dùng đồng ý, gọi service thực thi với snapshot/version đã preview.

Không hỏi xác nhận trước khi tính toán phạm vi. Nếu người dùng xác nhận trước khi biết sẽ xóa bao nhiêu bản ghi, sự đồng ý đó không gắn với một tác động cụ thể.

### 5.2. Kết hợp nhiều bước bằng ComponentFlow

Khi cần nhập thêm dữ liệu và xác nhận, ComponentFlow có thể kết nối nhiều component thành một flow. Ví dụ, flow có thể yêu cầu người dùng chọn môi trường, nhập lý do thay đổi rồi xác nhận cuối cùng.

~~~java
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withStringInput("reason")
            .name("Lý do thay đổi")
            .and()
        .withConfirmationInput("confirm")
            .name("Xác nhận triển khai lên production")
            .defaultValue(false)
            .and()
        .build();

ComponentFlow.ComponentFlowResult result = flow.run();
~~~

Các component chạy theo thứ tự khai báo. ComponentFlow cũng hỗ trợ điều hướng có điều kiện qua hàm next; nếu hàm trả null hoặc ID không tồn tại, flow dừng. Xem [Flow components — Spring Shell](https://docs.spring.io/spring-shell/reference/components/flow/index.html) và [ConfirmationInputSpec API](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/component/flow/ConfirmationInputSpec.html).

Flow giúp tổ chức input tương tác. Nó không tự tạo transaction, audit record hoặc kiểm tra quyền. Những trách nhiệm đó vẫn thuộc service và ứng dụng.

## 6. Xử lý command trong non-interactive mode

Automation, CI/CD và script thường không có người ngồi trước terminal để trả lời prompt. Một command chờ ConfirmationInput trong môi trường này có thể treo vô thời hạn hoặc thất bại vì không có terminal tương tác.

Với non-interactive mode, không nên tự động coi việc thiếu câu trả lời là đồng ý. Có thể thiết kế command automation yêu cầu một cờ xác nhận tường minh:

~~~text
storage purge-batch --bucket customer-archive --older-than-days 365 --yes
~~~

Quy tắc:

- Nếu chỉ có --dry-run, tạo preview và kết thúc.
- Nếu muốn thay đổi thật, yêu cầu --yes hoặc một approval token hợp lệ.
- Nếu thiếu xác nhận tường minh, từ chối trước khi gọi thao tác ghi.
- --yes chỉ bỏ qua prompt; nó không cấp quyền và không bỏ qua kiểm tra nghiệp vụ.
- Với thao tác cần phê duyệt hai người, --yes không thể thay thế approval workflow.

Ví dụ command batch:

~~~java
@ShellMethod(key = "storage purge-batch")
public String purgeBatch(
        @ShellOption("--bucket") String bucket,
        @ShellOption("--older-than-days") int olderThanDays,
        @ShellOption(value = "--dry-run", defaultValue = "false") boolean dryRun,
        @ShellOption(value = "--yes", defaultValue = "false") boolean yes) {

    PurgePreview preview = purgeService.previewPurge(bucket, olderThanDays);

    if (dryRun) {
        auditService.recordPreview(preview, currentActor.require());
        return previewFormatter.format(preview);
    }

    if (!yes) {
        auditService.recordRejected(
                "storage purge-batch", bucket, "explicit --yes is required");
        throw new IllegalArgumentException(
                "Refusing to purge data without explicit --yes");
    }

    return executePurge(preview, currentActor.require());
}
~~~

Đây là entry point dành cho automation nên không mở prompt. Command tương tác có thể dùng ConfirmationInput; cả hai entry point nên gọi chung một service thực thi để không tạo hai bộ quy tắc nghiệp vụ khác nhau.

Trong Spring Shell 4.x, runner được chọn ở cấp ứng dụng khi khởi động. Nếu chạy non-interactive, hãy thiết kế command để nhận đủ input từ arguments và từ chối khi thiếu xác nhận tường minh. Không dựa vào việc có thể đọc thêm từ terminal.

API component cũng thay đổi package giữa các major version. Trong 4.x, ConfirmationInput và ComponentFlow nằm dưới package org.springframework.shell.jline.tui.component và org.springframework.shell.jline.tui.component.flow; ứng dụng cần module JLine tương ứng để dùng các component này. Hãy đối chiếu import với minor version đang dùng, không sao chép package org.springframework.shell.component của 3.x.

## 7. Cờ dry-run và cờ yes phải có ý nghĩa độc lập

Hai cờ thường gặp:

- --dry-run: chỉ tính toán và trình bày tác động, không commit thay đổi.
- --yes: xác nhận rõ ràng cho một lần thực thi không tương tác.

Ma trận hành vi gợi ý:

| --dry-run | --yes | Hành vi |
|---|---|---|
| false | false | Phiên tương tác hỏi xác nhận; batch từ chối |
| true | false | Chỉ preview, không thay đổi dữ liệu |
| true | true | Vẫn chỉ preview, không thay đổi dữ liệu |
| false | true | Có thể thực thi sau khi kiểm tra quyền và điều kiện |

Không để --yes vô hiệu hóa --dry-run. Khi người dùng yêu cầu dry-run, hệ thống không được commit kể cả khi cờ yes cũng xuất hiện.

Đặt default của cả hai cờ là false. Tránh default yes, tránh một option có tên mơ hồ như --force mà không mô tả chính xác nó bỏ qua bước nào. Nếu có --force, tài liệu phải nêu rõ giới hạn và không để nó bỏ qua authorization, validation hoặc kiểm tra trạng thái.

## 8. Thực thi đúng kế hoạch đã xác nhận

Sau khi người dùng đồng ý, không nên chỉ gọi lại một câu truy vấn chung rồi thực hiện trên toàn bộ kết quả mới nhất. Service cần liên hệ execution với preview mà người dùng đã thấy.

Ví dụ:

~~~java
public PurgeResult executePurge(
        PurgePreview preview,
        UserIdentity actor) {

    authorization.requirePermission(actor, "storage:purge", preview.bucket());

    return transactionTemplate.execute(status -> {
        PurgeSelection current = repository.findPurgeCandidates(
                preview.bucket(), preview.filterDescription());

        if (!current.snapshotVersion().equals(preview.snapshotVersion())) {
            throw new PreviewExpiredException(
                    "Storage state changed; create a new preview");
        }

        return repository.deleteCandidates(current.ids());
    });
}
~~~

Đoạn code minh họa nguyên tắc, không phải một triển khai repository hoàn chỉnh. Trong ứng dụng thật, filter nên được lưu dưới dạng dữ liệu có kiểu thay vì chuỗi mô tả; snapshot version cần được tạo và kiểm tra theo cơ chế của kho dữ liệu.

Các điểm quan trọng:

- Service kiểm tra lại authorization theo actor và tài nguyên cụ thể.
- Service xác minh preview chưa hết hạn hoặc dữ liệu chưa thay đổi.
- Thao tác ghi và kiểm tra cạnh tranh phải được bảo vệ bằng transaction, lock hoặc optimistic concurrency phù hợp.
- Nếu phạm vi thay đổi, dừng và yêu cầu preview mới.
- Không dùng một preview do client gửi lên làm bằng chứng rằng người dùng đã được cấp quyền.

## 9. Xác nhận không thay thế authorization

Người dùng đồng ý không có nghĩa người dùng được phép. Một tài khoản có thể nhập --yes hoặc chọn Yes trong prompt nhưng vẫn không có quyền xóa dữ liệu của tenant khác.

Luồng kiểm tra cần tách biệt:

| Lớp | Câu hỏi |
|---|---|
| Authentication | Ai đang gọi command? |
| Authorization | Actor có quyền thực hiện hành động trên tài nguyên này không? |
| Preview | Tác động dự kiến là gì? |
| Confirmation | Actor có đồng ý với hành động và phạm vi đã trình bày không? |
| Execution guard | Trạng thái và quyền còn hợp lệ ngay lúc commit không? |
| Audit | Ai đã yêu cầu/xác nhận, quyết định nào được đưa ra và kết quả là gì? |

Service cần nhận actor từ ngữ cảnh xác thực đáng tin cậy. Không nhận một chuỗi --user-id từ command rồi mặc nhiên coi đó là danh tính đã xác thực.

Nếu người dùng có thể xác nhận một thao tác mà họ không có quyền thực hiện, prompt chỉ tạo cảm giác kiểm soát mà không bảo vệ tài nguyên.

## 10. Ghi nhận tác vụ bằng audit trail

Audit trail là lịch sử sự kiện có cấu trúc về các hành động quan trọng. Nó giúp trả lời:

- Ai đã yêu cầu thao tác?
- Tài nguyên hoặc phạm vi nào bị ảnh hưởng?
- Ai đã xác nhận hoặc từ chối?
- Thời điểm nào thao tác được bắt đầu và kết thúc?
- Hệ thống đã thực hiện bao nhiêu thay đổi?
- Kết quả thành công, thất bại hay bị hủy?
- Có lỗi hoặc chính sách nào ngăn thao tác?

Spring Shell không tự động tạo audit trail cho mọi command. Ứng dụng cần tích hợp audit service hoặc cơ chế event logging phù hợp.

Một audit event nên có các trường:

| Trường | Mục đích |
|---|---|
| eventId | Định danh duy nhất của event |
| operationId/correlationId | Liên kết các event thuộc cùng một lần thao tác |
| occurredAt | Thời điểm theo UTC |
| actorId | Danh tính đã xác thực của người thực hiện |
| action | Tên hành động, ví dụ storage.purge |
| target | Bucket, account, environment hoặc tài nguyên đích |
| scopeSummary | Phạm vi ảnh hưởng đã được preview |
| previewVersion | Snapshot/version đã được xác nhận |
| confirmation | Interactive yes, explicit flag, approval token hoặc declined |
| executionMode | Interactive, non-interactive hoặc automation |
| outcome | Previewed, cancelled, started, succeeded, failed hoặc rejected |
| reason | Lý do từ chối/thất bại đã được làm sạch |
| affectedCount | Số lượng thực tế được thay đổi nếu có |

Ví dụ record:

~~~json
{
  "eventId": "evt-8d31",
  "operationId": "op-20261126-0042",
  "occurredAt": "2026-11-26T15:20:31Z",
  "actorId": "operator-17",
  "action": "storage.purge",
  "target": "customer-archive",
  "scopeSummary": {
    "affectedObjects": 2480,
    "estimatedBytes": 19971597926
  },
  "previewVersion": "rev-8f3a",
  "confirmation": "interactive-yes",
  "executionMode": "interactive",
  "outcome": "succeeded",
  "affectedCount": 2480
}
~~~

Đây là schema minh họa. Không đưa password, access token, session cookie hoặc dữ liệu bí mật vào event. Chỉ lưu dữ liệu cá nhân khi có mục đích, quyền truy cập và thời hạn lưu phù hợp.

## 11. Ghi nhiều event theo vòng đời thao tác

Một event duy nhất ở cuối command thường không đủ để phân biệt thao tác bị hủy, bị từ chối hay đã bắt đầu nhưng thất bại. Với hành động quan trọng, nên ghi các mốc:

| Event | Khi nào ghi |
|---|---|
| PREVIEWED | Preview được tạo và trả cho người dùng |
| CONFIRMATION_DECLINED | Người dùng chọn No hoặc hủy prompt |
| EXECUTION_REJECTED | Không có xác nhận hoặc không đủ quyền |
| EXECUTION_STARTED | Đã qua kiểm tra và bắt đầu thay đổi |
| EXECUTION_SUCCEEDED | Thao tác đã commit thành công |
| EXECUTION_FAILED | Thao tác thất bại, kèm mã lỗi an toàn |

Không phải ứng dụng nào cũng cần tất cả event. Chọn tập event đủ để tái dựng vòng đời và phục vụ kiểm toán.

Một quy trình có thể ghi:

~~~text
15:20:01Z PREVIEWED          actor=operator-17 target=customer-archive count=2480
15:20:08Z CONFIRMATION_DECLINED actor=operator-17 target=customer-archive
~~~

Trong trường hợp này không có EXECUTION_STARTED hoặc EXECUTION_SUCCEEDED vì người dùng đã hủy.

Nếu command bị từ chối do thiếu --yes trong batch, ghi EXECUTION_REJECTED với lý do phù hợp. Không ghi thành công chỉ vì process kết thúc mà không có exception.

## 12. Phân biệt audit log với log vận hành

Log vận hành phục vụ debug và theo dõi hệ thống. Audit trail phục vụ truy vết hành động và trách nhiệm. Hai loại log có thể được xuất đến cùng một nền tảng nhưng không nên coi chúng là một.

| Log vận hành | Audit trail |
|---|---|
| Tập trung vào lỗi, latency, stack trace, metrics | Tập trung vào actor, action, target, decision và outcome |
| Có thể có mức debug/info/warn | Cần schema ổn định và chính sách lưu giữ rõ |
| Có thể lấy mẫu hoặc giảm chi tiết theo tải | Không tùy tiện bỏ event quan trọng |
| Dùng cho kỹ sư vận hành | Dùng cho vận hành, bảo mật và kiểm toán theo quyền |
| Stack trace có thể hữu ích | Reason phải được làm sạch và không lộ bí mật |

Không dùng câu log tự do như “user did something” làm audit record duy nhất. Hãy lưu event có cấu trúc để truy vấn theo actor, action, target, thời gian và operation ID.

Audit storage cần có kiểm soát truy cập, thời hạn lưu, sao lưu và cơ chế phát hiện sửa/xóa trái phép phù hợp với mức rủi ro. Với hệ thống có yêu cầu kiểm toán cao, cân nhắc kho append-only hoặc cơ chế integrity verification.

## 13. Gắn audit với transaction và xử lý lỗi

Audit record thành công cần phản ánh đúng trạng thái đã commit. Nếu ghi audit thành công trước khi transaction nghiệp vụ commit, có thể xuất hiện event “succeeded” dù dữ liệu thực tế đã rollback.

Một số lựa chọn:

**Cùng transaction:** ghi thay đổi nghiệp vụ và audit event trong cùng transaction database. Nếu transaction rollback, cả hai cùng rollback. Cách này bảo đảm nhất quán khi cùng một database hỗ trợ transaction phù hợp.

**Transactional outbox:** ghi thay đổi nghiệp vụ và một outbox event trong cùng transaction. Một publisher đọc outbox rồi chuyển event tới hệ thống audit/log tập trung. Cách này hữu ích khi audit store là hệ thống riêng.

**Event bắt đầu và kết quả:** ghi EXECUTION_STARTED trước thao tác, rồi ghi SUCCEEDED hoặc FAILED sau khi biết kết quả. Nếu process chết giữa chừng, event started chưa có kết quả là tín hiệu cần đối soát.

Với thao tác có side effect ở hệ thống bên ngoài, transaction database không thể tự rollback side effect đó. Cần idempotency key, trạng thái operation, retry có kiểm soát và quy trình reconciliation.

Không nuốt lỗi khi audit bắt buộc phải ghi. Nếu audit store không sẵn sàng, chính sách cần xác định hành động có được phép tiếp tục hay phải dừng. Với thao tác có ảnh hưởng lớn, nhiều hệ thống chọn fail-closed: không thực hiện thay đổi nếu không thể ghi nhận theo yêu cầu.

## 14. Chống chạy lặp và retry ngoài ý muốn

Script, scheduler và CI có thể gửi lại cùng command khi timeout hoặc không nhận được kết quả. Nếu command xóa, tạo hoặc triển khai không idempotent, retry có thể gây tác động lặp.

Có thể dùng operation ID hoặc idempotency key:

~~~text
storage purge-batch \
  --bucket customer-archive \
  --older-than-days 365 \
  --request-id purge-20261126-0042 \
  --yes
~~~

Service lưu trạng thái operation ID và từ chối hoặc trả lại kết quả đã có nếu cùng request được gửi lại. Key phải được ràng buộc với actor, action và payload đã chuẩn hóa; không cho phép tái sử dụng cùng key với nội dung khác.

Với thao tác theo lô, cần xác định rõ tính nguyên tử:

- Toàn bộ batch thành công hoặc thất bại.
- Thành công từng phần và trả danh sách lỗi.
- Chia thành nhiều chunk có checkpoint.

Audit trail phải phản ánh chính sách đó, đặc biệt khi một phần dữ liệu đã thay đổi trước khi lỗi xảy ra.

## 15. Quy trình xử lý từ command đến service

Một command có thể tổ chức theo cấu trúc:

~~~java
public String purgeInteractive(String bucket, int olderThanDays) {
    UserIdentity actor = currentActor.require();

    authorization.requirePermission(actor, "storage:purge", bucket);

    PurgePreview preview = purgeService.previewPurge(bucket, olderThanDays);
    auditService.recordPreview(preview, actor);

    terminalOutput.print(previewFormatter.format(preview));

    if (!confirmationService.confirm(preview)) {
        auditService.recordCancelled(preview, actor);
        return "Đã hủy. Không có dữ liệu nào bị thay đổi.";
    }

    PurgeResult result = purgeService.executePurge(preview, actor);
    auditService.recordSucceeded(preview, result, actor);

    return "Đã xóa " + result.affectedObjects() + " object.";
}
~~~

Đây là cấu trúc minh họa ở mức ứng dụng; các interface currentActor, authorization, terminalOutput, confirmationService và auditService là thành phần do dự án định nghĩa. Spring Shell cung cấp cơ chế nhận command và component tương tác, còn các dịch vụ này cần được triển khai theo hệ thống cụ thể.

Không để command method trở thành nơi duy nhất bảo vệ thao tác. Service thực thi phải tự kiểm tra quyền, snapshot/version và tính hợp lệ. Nếu service được gọi từ REST, scheduler hoặc message consumer, các quy tắc vẫn phải có hiệu lực.

## 16. Xử lý từ chối, hủy và lỗi

Ba tình huống này cần được phân biệt:

| Tình huống | Ý nghĩa | Hành vi |
|---|---|---|
| Declined/cancelled | Người dùng đã xem preview nhưng không đồng ý | Không thực thi, ghi nhận hủy |
| Rejected | Thiếu quyền, thiếu --yes hoặc vi phạm policy | Từ chối trước khi thay đổi |
| Failed | Đã bắt đầu thực thi nhưng xảy ra lỗi | Ghi nhận thất bại và trạng thái thực tế |

Không coi Cancelled là Failed. Người dùng chọn No là một kết quả hợp lệ của quy trình an toàn.

Không hiển thị stack trace hoặc thông tin nội bộ trong terminal production. Có thể trả thông báo dễ hiểu và gắn operation ID để người vận hành tra cứu audit/log:

~~~text
Không thể thực hiện thao tác vì dữ liệu đã thay đổi sau preview.
Hãy tạo preview mới. Operation: op-20261126-0042
~~~

Nếu một phần thao tác đã thành công trước khi lỗi, output và audit phải nêu rõ phần đã thay đổi. Không báo “không có thay đổi” khi hệ thống đã commit một phần.

## 17. Kiểm thử preview, confirmation và audit

Spring Shell cung cấp test utilities để gửi command, mô phỏng input và kiểm tra output. Trong Spring Shell 4.0.3, tài liệu mô tả ShellTest, ShellTestClient, ShellScreen, ShellAssertions và ShellInputProvider. [Testing — Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/testing.html).

Kiểm thử nên bao gồm nhiều lớp:

### 17.1. Unit test cho preview service

- Preview không gọi repository write method.
- Bộ lọc và phạm vi preview khớp với execution.
- affected count và estimated size được tính đúng.
- Snapshot/version được tạo và giữ trong preview.
- Preview không tạo reservation hoặc gửi thông báo thật.

### 17.2. Unit test cho confirmation policy

- Giá trị mặc định của prompt là No.
- Câu trả lời No không gọi service thực thi.
- Câu trả lời Yes chỉ tiếp tục sau khi preview đã hiển thị.
- Typed confirmation phải khớp chính xác nếu policy yêu cầu.
- Hủy prompt hoặc mất terminal không được diễn giải thành Yes.

### 17.3. Integration test cho command

- --dry-run chỉ gọi preview và không gọi mutation.
- --dry-run kết hợp --yes vẫn không thay đổi dữ liệu.
- Interactive No không thực hiện thao tác.
- Interactive Yes thực hiện đúng phạm vi preview.
- Non-interactive thiếu --yes bị từ chối và không chờ input.
- Non-interactive có --yes vẫn kiểm tra authorization.
- Snapshot thay đổi sau preview làm execution bị từ chối.
- Quyền bị thu hồi trước commit làm execution bị từ chối.

### 17.4. Kiểm thử audit

- Preview tạo event PREVIEWED.
- Người dùng hủy tạo event CONFIRMATION_DECLINED.
- Thiếu --yes tạo event EXECUTION_REJECTED.
- Bắt đầu thao tác tạo EXECUTION_STARTED.
- Commit thành công tạo EXECUTION_SUCCEEDED.
- Lỗi thực thi tạo EXECUTION_FAILED.
- Operation ID liên kết được các event.
- Audit không chứa password, token hoặc bí mật.
- Retry cùng idempotency key không tạo side effect lặp.

Ma trận kiểm thử tổng hợp:

| Kịch bản | Thay đổi dữ liệu | Audit mong đợi |
|---|---|---|
| Preview bình thường | Không | PREVIEWED |
| Dry-run | Không | PREVIEWED hoặc DRY_RUN_COMPLETED |
| Người dùng chọn No | Không | CONFIRMATION_DECLINED |
| Batch thiếu --yes | Không | EXECUTION_REJECTED |
| Không có quyền | Không | EXECUTION_REJECTED |
| Yes và điều kiện còn hợp lệ | Có | STARTED, SUCCEEDED |
| Snapshot đã thay đổi | Không | EXECUTION_REJECTED/FAILED theo policy |
| Lỗi giữa chừng | Có thể một phần | STARTED, FAILED và thông tin phần đã commit |

Với interactive component, dùng test input provider để mô phỏng câu trả lời. Với non-interactive execution, test ở cấp process hoặc runner để xác nhận chương trình kết thúc và không chờ terminal input.

## 18. Những lỗi thường gặp

### Dry-run vẫn tạo side effect

Kiểm tra toàn bộ luồng, không chỉ câu lệnh delete/update cuối cùng. Gửi email, đặt reservation, phát message hoặc ghi trạng thái phụ cũng là side effect.

### Xác nhận trước khi hiển thị phạm vi

Người dùng không biết mình đang đồng ý với điều gì. Hãy tạo và trình bày preview trước, rồi mới hỏi.

### Prompt mặc định là Yes

Người dùng có thể nhấn Enter theo thói quen và vô tình thực hiện thao tác. Dùng default false và yêu cầu hành động xác nhận rõ ràng.

### ConfirmationInput được gọi trong batch

Không có terminal tương tác có thể khiến command treo hoặc lỗi. Tách đường chạy interactive và automation, hoặc dùng policy nhận biết execution mode; non-interactive phải yêu cầu xác nhận tường minh.

### --yes bỏ qua authorization

--yes chỉ biểu thị xác nhận cho một lần chạy. Service vẫn phải xác thực actor, kiểm tra quyền và trạng thái.

### Preview cũ được dùng để thực thi

Dữ liệu có thể thay đổi giữa hai thời điểm. Gắn preview với version hoặc tính toán lại; từ chối và yêu cầu preview mới khi phạm vi khác.

### Chỉ ghi audit sau khi hoàn tất

Nếu process chết giữa chừng, không có dấu vết cho biết thao tác đã bắt đầu. Ghi event bắt đầu và event kết quả theo chính sách.

### Audit event được ghi trước commit nhưng không đồng bộ

Có thể ghi thành công dù transaction rollback. Dùng cùng transaction hoặc transactional outbox khi cần nhất quán.

### Ghi cả command line vào log

Command có thể chứa token hoặc thông tin nhạy cảm. Ghi tham số đã chuẩn hóa và làm sạch; không lưu bí mật.

### Coi Cancelled là Failed

Người dùng chọn No là một kết quả hợp lệ. Ghi nhận trạng thái cancelled riêng.

### Retry gây thực thi lặp

Dùng idempotency key/operation ID, kiểm tra trạng thái operation và thiết kế service an toàn khi nhận lại request.

## 19. Checklist trước khi phát hành command có ảnh hưởng lớn

- [ ] Command có mô tả rõ đối tượng và phạm vi tác động.
- [ ] Preview chỉ đọc và không có side effect.
- [ ] Preview hiển thị môi trường, đối tượng, số lượng, điều kiện lọc và hậu quả.
- [ ] Preview có version/snapshot hoặc cơ chế phát hiện thay đổi.
- [ ] Dry-run không commit dù có --yes.
- [ ] Confirmation chỉ xuất hiện sau khi người dùng thấy preview.
- [ ] Giá trị mặc định của xác nhận là No.
- [ ] Non-interactive không chờ prompt và yêu cầu xác nhận tường minh.
- [ ] --yes không bỏ qua authentication, authorization hoặc validation.
- [ ] Service kiểm tra lại quyền và trạng thái ngay trước commit.
- [ ] Thao tác có transaction, lock hoặc concurrency control phù hợp.
- [ ] Có idempotency key hoặc cơ chế chống retry gây lặp khi cần.
- [ ] Audit ghi actor, action, target, thời điểm, decision và outcome.
- [ ] Audit phân biệt preview, cancelled, rejected, started, succeeded và failed.
- [ ] Audit không chứa password, token hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Có chính sách lưu giữ, quyền đọc và bảo vệ tính toàn vẹn audit.
- [ ] Có test cho dry-run, Yes, No, batch, lỗi, stale preview và audit.

## 20. Tự kiểm tra

**Câu 1.** Preview khác execution như thế nào?

**Gợi ý trả lời:** Preview tính toán và trình bày tác động dự kiến, không thay đổi dữ liệu nghiệp vụ. Execution thực hiện thay đổi thật sau khi qua các kiểm tra cần thiết.

**Câu 2.** Vì sao giá trị mặc định của ConfirmationInput nên là false?

**Gợi ý trả lời:** Để thao tác không được chấp nhận chỉ vì người dùng nhấn Enter hoặc không chủ động chọn Yes.

**Câu 3.** Vì sao không nên mở prompt xác nhận trong non-interactive mode?

**Gợi ý trả lời:** Automation không có người trả lời prompt; command có thể treo hoặc thất bại. Hãy yêu cầu cờ xác nhận tường minh như --yes và từ chối nếu thiếu.

**Câu 4.** --yes có thay thế authorization không?

**Gợi ý trả lời:** Không. Nó chỉ biểu thị xác nhận thực thi trong một lần gọi. Service vẫn phải xác thực actor và kiểm tra quyền trên tài nguyên.

**Câu 5.** Vì sao phải kiểm tra lại snapshot sau khi người dùng xác nhận?

**Gợi ý trả lời:** Dữ liệu hoặc quyền có thể thay đổi giữa preview và execution. Nếu phạm vi đã thay đổi, cần dừng và yêu cầu preview/xác nhận mới.

**Câu 6.** Audit event nào nên được ghi khi người dùng chọn No?

**Gợi ý trả lời:** Ghi event xác nhận bị từ chối hoặc thao tác bị hủy, chẳng hạn CONFIRMATION_DECLINED; không ghi EXECUTION_SUCCEEDED.

**Câu 7.** Làm thế nào để audit phản ánh đúng transaction?

**Gợi ý trả lời:** Ghi audit trong cùng transaction hoặc dùng transactional outbox; với thao tác dài hay side effect ngoài database, ghi mốc started và kết quả sau đó.

## Kết luận

Tác vụ có ảnh hưởng lớn cần một quy trình rõ ràng từ preview đến audit. Preview phải chỉ đọc và cho người dùng thấy đúng phạm vi; confirmation phải gắn với hành động cụ thể và mặc định từ chối; execution phải kiểm tra lại quyền, snapshot và điều kiện ngay trước khi thay đổi; audit trail phải ghi được ai yêu cầu, ai xác nhận và kết quả thực tế.

Spring Shell 3.4 cung cấp ConfirmationInput và ComponentFlow để xây dựng trải nghiệm xác nhận trong phiên tương tác. Với automation, hãy yêu cầu xác nhận tường minh qua arguments và không chờ prompt. Các cơ chế này không thay thế authorization, transaction hoặc audit service. Khi những trách nhiệm đó được đặt đúng tầng và kiểm thử riêng, CLI có thể thực hiện thao tác quan trọng một cách dễ hiểu, có kiểm soát và truy vết được.

## Tài liệu tham khảo

- [Spring Shell 3.4.3 — Confirmation component](https://docs.spring.io/spring-shell/reference/3.4/components/ui/confirmation.html)
- [Spring Shell 3.4.3 — Flow components](https://docs.spring.io/spring-shell/reference/components/flow/index.html)
- [Spring Shell 3.4.3 — ConfirmationInput API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/ConfirmationInput.html)
- [Spring Shell 3.4.3 — ComponentFlow API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.html)
- [Spring Shell 4.0.3 — ConfirmationInput API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/ConfirmationInput.html)
- [Spring Shell 4.0.3 — ComponentFlow API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/flow/ComponentFlow.html)
- [Spring Shell 4.0.3 — Testing](https://docs.spring.io/spring-shell/reference/testing.html)
