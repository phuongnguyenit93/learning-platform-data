# Lập lịch function bằng EventBridge Scheduler

AWS Lambda thường được kích hoạt bởi HTTP request, message hoặc sự kiện từ dịch vụ AWS. Tuy nhiên, nhiều nghiệp vụ cần chạy theo thời gian: tổng hợp báo cáo mỗi sáng, đóng phiên hết hạn, gửi nhắc việc vào một ngày cụ thể, chạy tác vụ đối soát cuối tháng hoặc khởi động một workflow sau vài giờ. **Amazon EventBridge Scheduler** cung cấp dịch vụ lập lịch được quản lý để gọi Lambda và nhiều loại đích AWS khác theo lịch một lần hoặc lặp lại.

Scheduler giúp tách thời điểm chạy khỏi mã nghiệp vụ. Function chỉ tập trung xử lý event; Scheduler chịu trách nhiệm giữ lịch, xác định thời điểm kích hoạt, gửi yêu cầu tới target và áp dụng chính sách retry khi không thể giao yêu cầu. Thiết kế vẫn phải tính đến việc giao event trễ hoặc lặp, quyền IAM, giới hạn invocation, múi giờ, thời gian chạy của function và cách quan sát lỗi.

Trong ứng dụng Java serverless, handler cần xử lý event có cấu trúc, xác thực dữ liệu cần thiết và thực hiện công việc theo cách idempotent. Không dùng thread nền hoặc vòng lặp sleep bên trong Lambda để chờ tới giờ chạy. Một function kết thúc invocation không được bảo đảm tiếp tục tồn tại để thực hiện công việc trong tương lai.

## 1. EventBridge Scheduler trong kiến trúc serverless

EventBridge Scheduler là dịch vụ lập lịch độc lập trong hệ sinh thái Amazon EventBridge. Bạn tạo một schedule, chỉ định biểu thức thời gian, múi giờ, cửa sổ linh hoạt và target. Đến thời điểm phù hợp, Scheduler gọi API của target bằng execution role được chỉ định.

Một luồng đơn giản:

~~~mermaid
flowchart LR
    A["EventBridge Scheduler"] -->|"Đến thời điểm đã đặt"| B["Assume execution role"]
    B -->|"Invoke API"| C["AWS Lambda function"]
    C --> D["Xử lý nghiệp vụ"]
    D --> E[("DynamoDB / S3 / database")]
    A -.->|"Lỗi giao target"| F["Retry policy"]
    F -.-> G["Scheduler DLQ"]
    C -.->|"Lỗi khi function chạy"| H["Lambda async retry / destination"]
~~~

Các thành phần chính:

| Thành phần | Trách nhiệm |
|---|---|
| Schedule | Lưu biểu thức thời gian, timezone, trạng thái và cấu hình giao target |
| Schedule group | Nhóm schedule để tổ chức, tagging và quản lý |
| Schedule expression | Mô tả lịch chạy một lần hoặc lặp lại |
| Flexible time window | Cho phép phân tán thời điểm giao target trong một khoảng |
| Target | Tài nguyên hoặc API được gọi, ví dụ Lambda, SQS hay Step Functions |
| Execution role | IAM role Scheduler assume để gọi target |
| Retry policy | Giới hạn số lần thử và tuổi tối đa của lần giao target |
| Dead-letter queue (DLQ) | Nhận thông tin/event khi Scheduler không thể giao target theo policy |
| Action after completion | Quy định có xóa schedule một lần sau khi hoàn tất hay giữ lại |

Scheduler là dịch vụ quản lý lịch; Lambda vẫn là nơi chạy mã nghiệp vụ. Mỗi schedule có thể kích hoạt cùng một function với payload khác nhau, hoặc nhiều schedule có thể gọi các function chuyên biệt.

## 2. EventBridge Scheduler và scheduled rules

EventBridge có scheduled rules truyền thống, nhưng Scheduler là lựa chọn chuyên biệt hơn cho nhu cầu lập lịch mới. Scheduled rule thuộc EventBridge rule và phát event vào event bus hoặc target theo cơ chế rule. EventBridge Scheduler quản lý trực tiếp schedule, hỗ trợ lịch một lần, timezone, flexible time window, retry policy và DLQ ở cấp schedule.

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Chạy function một lần tại thời điểm xác định | EventBridge Scheduler |
| Chạy theo cron với múi giờ địa phương | EventBridge Scheduler |
| Chạy theo chu kỳ rate | EventBridge Scheduler |
| Lập lịch số lượng lớn với chính sách retry/DLQ riêng | EventBridge Scheduler |
| Lọc event theo nội dung rồi định tuyến tới nhiều target | EventBridge rule trên event bus |
| Kết hợp sự kiện nghiệp vụ với nhiều consumer | EventBridge event bus và rules |

Đừng nhầm lịch với định tuyến event. Scheduler trả lời “khi nào cần gọi target”; EventBridge event bus và rule trả lời “event nào phù hợp với điều kiện nào sẽ được định tuyến tới đâu”. Hai cơ chế có thể kết hợp: Scheduler có thể kích hoạt một target phát event, sau đó event bus định tuyến event tới các consumer.

## 3. Ba loại schedule expression

Scheduler hỗ trợ lịch một lần (at), lịch theo khoảng thời gian (rate) và lịch dạng cron (cron).

### Lịch một lần: at

Dùng **at** khi một tác vụ chỉ cần chạy tại một thời điểm:

~~~text
at(2026-12-01T09:00:00)
~~~

Có thể chỉ định múi giờ bằng thuộc tính ScheduleExpressionTimezone, ví dụ **Asia/Ho_Chi_Minh**. Khi đó thời gian trong biểu thức được hiểu theo timezone đã cấu hình. Lịch một lần phù hợp với nhắc việc, xử lý đơn hàng đến hạn, hết hạn link tải hoặc khởi động một job đã được lên lịch trước.

Một schedule at không phải cơ chế timer chính xác đến từng mili giây. Khi flexible time window tắt, Scheduler thường giao target trong vòng 60 giây kể từ thời điểm đã đặt; nếu bật cửa sổ linh hoạt, việc giao có thể diễn ra trong khoảng đó. Khi cần deadline chính xác đến giây hoặc mili giây, cần thiết kế cơ chế chuyên dụng và kiểm tra SLA thực tế.

### Lịch theo khoảng thời gian: rate

Dùng **rate** cho chu kỳ lặp:

~~~text
rate(5 minutes)
rate(1 hour)
rate(1 day)
~~~

Rate biểu diễn khoảng cách giữa các lần chạy, phù hợp với công việc định kỳ không phụ thuộc vào giờ trên lịch. Nếu cần chạy lúc 09:00 mỗi ngày theo giờ địa phương, cron thường diễn đạt đúng ý nghĩa hơn rate(1 day), vì rate là chu kỳ thời gian chứ không phải một mốc giờ trên lịch.

### Lịch cron

Cron phù hợp với lịch theo phút, giờ, ngày trong tháng, tháng, ngày trong tuần và năm. Cấu trúc cron của Scheduler có sáu trường:

~~~text
cron(minutes hours day-of-month month day-of-week year)
~~~

Ví dụ:

| Yêu cầu | Biểu thức |
|---|---|
| Mỗi ngày lúc 09:00 | cron(0 9 * * ? *) |
| Thứ Hai đến thứ Sáu lúc 09:00 | cron(0 9 ? * MON-FRI *) |
| Ngày đầu tháng lúc 08:00 | cron(0 8 1 * ? *) |
| Mỗi Chủ nhật lúc 23:30 | cron(30 23 ? * SUN *) |
| Mỗi giờ vào phút thứ 15 | cron(15 * * * ? *) |

Trong biểu thức cron của AWS, dấu hỏi (?) được dùng ở trường day-of-month hoặc day-of-week để biểu thị không chỉ định trường đó. Thông thường, chỉ một trong hai trường này được xác định cụ thể. Hãy kiểm tra biểu thức bằng tài liệu cú pháp của Scheduler và thử trên môi trường không production trước khi bật lịch thật.

## 4. Múi giờ và thời điểm chạy

Nếu không chỉ định ScheduleExpressionTimezone, lịch được hiểu theo UTC. Khi nghiệp vụ dùng giờ địa phương, hãy khai báo tên timezone theo cơ sở dữ liệu IANA, chẳng hạn:

~~~text
ScheduleExpression: cron(0 9 * * ? *)
ScheduleExpressionTimezone: Asia/Ho_Chi_Minh
~~~

Dùng timezone có tên thay vì tự cộng hoặc trừ số giờ trong mã. Cách này giúp lịch thể hiện đúng ý nghĩa nghiệp vụ và tránh việc phải tự sửa cron khi quy tắc múi giờ thay đổi.

Với khu vực có daylight saving time (DST), cần kiểm tra hành vi của lịch tại thời điểm đồng hồ chuyển tiếp. Theo quy tắc Scheduler, một lịch cron rơi vào giờ địa phương không tồn tại khi đồng hồ tiến lên sẽ bị bỏ qua; khi đồng hồ lùi và một giờ xuất hiện hai lần, lịch trong giờ lặp chỉ chạy một lần. Nếu nghiệp vụ yêu cầu một lần chạy theo ngày lịch, hãy xác định rõ kỳ vọng và kiểm thử các mốc chuyển DST. Việt Nam hiện không áp dụng DST, nhưng ứng dụng chạy đa quốc gia vẫn cần xử lý điều này.

Các điểm cần phân biệt:

- **UTC timestamp:** mốc thời gian tuyệt đối để lưu và đối soát.
- **Timezone:** quy tắc diễn giải giờ lịch của schedule.
- **Scheduled time:** thời điểm mà schedule dự kiến kích hoạt.
- **Actual delivery time:** thời điểm Scheduler thực sự gửi yêu cầu tới target.

Không dùng thời điểm function bắt đầu chạy làm mốc nghiệp vụ nếu cần biết kỳ chạy dự kiến. Hãy truyền scheduled time vào payload để job có thể xử lý đúng kỳ, kể cả khi target được gọi trễ.

## 5. Flexible time window và độ chính xác

Flexible time window cho phép Scheduler phân tán việc giao target trong một khoảng thời gian thay vì dồn tất cả schedule vào đúng một thời điểm. Điều này giúp giảm burst khi nhiều schedule có cùng mốc chạy và giảm áp lực lên target.

Hai chế độ:

- **OFF:** không yêu cầu Scheduler phân tán trong một cửa sổ linh hoạt. Scheduler vẫn có độ chính xác giao target theo phút, không phải thời gian thực tuyệt đối.
- **FLEXIBLE:** chỉ định MaximumWindowInMinutes để Scheduler chọn thời điểm giao target trong khoảng đã cấu hình.

Ví dụ, báo cáo nội bộ có thể chạy trong cửa sổ 15 phút sau 09:00 mà không ảnh hưởng nghiệp vụ. Một tác vụ thanh toán đến hạn hoặc gửi thông báo tại thời điểm cam kết với khách hàng có thể cần cửa sổ linh hoạt tắt, đồng thời vẫn phải chấp nhận độ chính xác và latency thực tế của dịch vụ.

Không bật flexible window chỉ để “tránh lỗi giờ”. Đây là lựa chọn đánh đổi giữa phân tán tải và thời điểm thực thi. Hãy xác định độ trễ tối đa nghiệp vụ chấp nhận trước khi cấu hình.

## 6. Schedule group và quản lý nhiều lịch

Schedule group là namespace để tổ chức schedule. Có thể tạo nhóm theo ứng dụng, môi trường hoặc domain nghiệp vụ, ví dụ:

~~~text
orders-prod
billing-prod
reporting-staging
customer-reminders
~~~

Nhóm giúp quản lý danh sách schedule, gắn tag, phân tách quyền thao tác và quan sát theo domain. Tên schedule cần duy nhất trong phạm vi group. ARN của schedule bao gồm Region, account, group và tên schedule.

Một số nguyên tắc:

- Tách group theo ranh giới ownership và môi trường.
- Dùng naming convention dễ tìm và có ý nghĩa nghiệp vụ.
- Gắn tag owner, application, environment và cost center.
- Giới hạn quyền tạo, cập nhật, bật/tắt và xóa schedule theo group khi phù hợp.
- Tránh tạo một group khổng lồ nếu nhiều team cần quyền vận hành khác nhau.
- Xóa hoặc dọn schedule một lần sau khi hoàn tất nếu không cần lưu lại.

Schedule group không thay thế IAM policy. Quyền thực tế vẫn phụ thuộc principal gọi API Scheduler, resource ARN và policy tương ứng.

## 7. Target và execution role

Target là API hoặc tài nguyên Scheduler gọi khi tới giờ. Các target được hỗ trợ gồm Lambda, SQS, Step Functions và nhiều dịch vụ AWS khác; Scheduler cũng hỗ trợ một số API AWS thông qua universal target.

Khi target là Lambda, Scheduler cần một execution role để gọi lambda:InvokeFunction. Role này khác với execution role của Lambda:

- **Scheduler execution role:** Scheduler assume để gọi Lambda hoặc gửi message tới target.
- **Lambda execution role:** Lambda assume khi chạy handler để truy cập database, S3, Secrets Manager và các dịch vụ khác.

Luồng quyền:

~~~mermaid
flowchart TD
    S["EventBridge Scheduler service"] -->|"sts:AssumeRole"| R["Scheduler execution role"]
    R -->|"lambda:InvokeFunction"| L["Lambda function / alias"]
    L -->|"Assume execution role"| LR["Lambda execution role"]
    LR -->|"Read/write theo policy"| D[("DynamoDB / S3 / services")]
~~~

Trust policy của Scheduler role cần cho phép service principal scheduler.amazonaws.com assume role. Nên giới hạn bằng source account và schedule group ARN khi phù hợp để giảm nguy cơ confused deputy.

Ví dụ trust policy minh họa:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "scheduler.amazonaws.com"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "123456789012"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:scheduler:ap-southeast-1:123456789012:schedule-group/orders-prod"
        }
      }
    }
  ]
}
~~~

Policy quyền của role có thể chỉ cho phép gọi đúng function hoặc alias:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:daily-summary:live"
    }
  ]
}
~~~

Nếu target là SQS, Step Functions hoặc API AWS khác, quyền cần thiết sẽ khác. Không cấp lambda:* hoặc quyền quản trị rộng cho Scheduler role nếu chỉ cần invoke một function.

## 8. Payload và context attributes

Scheduler gửi input tới target. Với Lambda, input thường là JSON mà handler nhận được. Payload nên mô tả công việc cần làm, không chứa secret hoặc dữ liệu nhạy cảm không cần thiết.

Ví dụ event cho function tổng hợp báo cáo:

~~~json
{
  "jobType": "DAILY_SUMMARY",
  "scheduledTime": "<aws.scheduler.scheduled-time>",
  "executionId": "<aws.scheduler.execution-id>",
  "attemptNumber": "<aws.scheduler.attempt-number>",
  "scheduleArn": "<aws.scheduler.schedule-arn>"
}
~~~

Scheduler hỗ trợ context attributes để chèn thông tin về lần thực thi vào input. Một số thuộc tính hữu ích:

- **<aws.scheduler.scheduled-time>:** thời điểm schedule dự kiến chạy.
- **<aws.scheduler.execution-id>:** định danh lần thực thi.
- **<aws.scheduler.attempt-number>:** số lần thử giao target.
- **<aws.scheduler.schedule-arn>:** ARN của schedule.
- **<aws.scheduler.target-arn>:** ARN của target.
- **<aws.scheduler.group-name>:** tên schedule group.

Các placeholder được Scheduler thay thế khi gửi input. Hãy dùng đúng tên attribute và định dạng JSON hợp lệ. Không đặt placeholder trong một chuỗi JSON không hợp lệ hoặc dùng giá trị từ event như bằng chứng xác thực danh tính.

Đối với lịch định kỳ, scheduled time giúp xác định kỳ dữ liệu cần xử lý. Ví dụ, nếu một lần chạy bị trễ qua nửa đêm, job vẫn có thể tổng hợp ngày dự kiến thay vì lấy ngày hiện tại từ đồng hồ của function.

## 9. Retry và DLQ: phân biệt lỗi giao target với lỗi chạy function

Có hai lớp lỗi khác nhau khi Scheduler gọi Lambda bất đồng bộ.

**Lớp 1 – Scheduler không giao được yêu cầu tới target.** Ví dụ, Lambda API throttling, lỗi quyền hoặc dịch vụ target tạm thời không sẵn sàng. Retry policy của Scheduler điều khiển số lần thử và tuổi tối đa của yêu cầu. Nếu không giao được sau policy, Scheduler có thể gửi event tới DLQ được cấu hình.

**Lớp 2 – Lambda đã nhận event nhưng handler chạy thất bại.** Với invocation type bất đồng bộ, Lambda quản lý việc retry thực thi theo cấu hình asynchronous invocation của function. DLQ hoặc on-failure destination của Lambda xử lý kết quả thất bại ở lớp này.

~~~mermaid
flowchart TD
    A["Scheduler đến giờ"] --> B["Gửi Invoke request"]
    B --> C{"Lambda API nhận request?"}
    C -->|"Không"| D["Scheduler retry policy"]
    D --> E{"Còn retry?"}
    E -->|"Có"| B
    E -->|"Không"| F["Scheduler DLQ"]
    C -->|"Có, accepted"| G["Lambda async queue"]
    G --> H["Function handler"]
    H --> I{"Handler thành công?"}
    I -->|"Có"| J["Hoàn tất"]
    I -->|"Không"| K["Lambda async retry policy"]
    K --> L{"Còn retry?"}
    L -->|"Có"| H
    L -->|"Không"| M["Lambda DLQ / on-failure destination"]
~~~

Với target Lambda, cần xác định invocation type phù hợp. Nếu dùng **Event**, Lambda nhận event bất đồng bộ; Scheduler coi việc target chấp nhận yêu cầu là giao thành công. Retry của Scheduler không thay thế retry thực thi bất đồng bộ của Lambda.

Điều này có ý nghĩa khi vận hành: Scheduler DLQ có thể trống trong khi handler vẫn thất bại và event đi vào Lambda failure destination. Hãy theo dõi cả hai lớp.

Retry cần có giới hạn và backoff. Không dùng retry để che giấu lỗi cấu hình quyền hoặc payload sai. Khi phát lại event từ DLQ, giữ định danh nghiệp vụ và bảo đảm handler idempotent.

## 10. Idempotency cho lịch một lần và lịch lặp

Scheduler có thể giao target nhiều lần trong một số tình huống retry hoặc lỗi mạng. Một schedule một lần không có nghĩa side effect chắc chắn chỉ xảy ra một lần. Lịch định kỳ còn có thể chạy lại khi event được giao lại hoặc function retry.

Thiết kế idempotency theo **lần chạy nghiệp vụ**, không chỉ theo số lần invocation. Với lịch tổng hợp hằng ngày, khóa có thể là:

~~~text
scheduleArn + scheduledTime + jobType
~~~

Không nên dùng attempt number làm idempotency key vì các lần thử khác nhau thuộc cùng một lần chạy dự kiến.

Một Java handler minh họa:

~~~java
public record ScheduledJobEvent(
        String jobType,
        String scheduledTime,
        String executionId,
        String attemptNumber,
        String scheduleArn) {}

public final class DailySummaryHandler
        implements RequestHandler<ScheduledJobEvent, Void> {

    private final IdempotencyService idempotency;
    private final SummaryService summaryService;

    @Override
    public Void handleRequest(
            ScheduledJobEvent event,
            Context context) {

        String key = event.scheduleArn()
                + "#" + event.scheduledTime()
                + "#" + event.jobType();

        idempotency.executeOnce(key, () ->
                summaryService.generateForScheduledTime(
                        event.jobType(),
                        Instant.parse(event.scheduledTime())
                )
        );

        return null;
    }
}
~~~

Các class service trong ví dụ là abstraction của ứng dụng. executeOnce phải được triển khai bằng thao tác atomic trong kho trạng thái bền vững, có trạng thái PROCESSING/COMPLETED, lease hoặc cơ chế phục hồi nếu worker chết giữa chừng. Chỉ kiểm tra “key đã tồn tại chưa” rồi ghi riêng ở hai bước là không đủ vì hai invocation đồng thời có thể cùng vượt qua kiểm tra.

Nếu job gọi dịch vụ thanh toán hoặc tạo tài nguyên bên ngoài, truyền idempotency key xuống dependency khi dịch vụ hỗ trợ. Nếu không thể tạo transaction xuyên hệ thống, lưu trạng thái từng bước và có quy trình đối soát hoặc compensation.

## 11. Lập lịch một lần và dọn schedule sau khi hoàn tất

Schedule **at** thường chỉ cần chạy một lần. Sau khi lần thực thi hoàn tất, schedule vẫn có thể còn tồn tại như một tài nguyên đã hoàn thành. Thuộc tính ActionAfterCompletion cho phép chọn hành động sau lần chạy cuối, thường dùng **DELETE** để tự xóa schedule một lần sau khi hoàn tất.

Dùng DELETE khi schedule chỉ là một timer tạm thời cho một job. Giữ schedule khi cần kiểm tra cấu hình hoặc quản trị vòng đời theo quy trình riêng. Với lịch định kỳ, không xóa sau mỗi lần chạy vì lịch còn những lần tiếp theo.

Khi tạo schedule cho một đơn hàng đến hạn, có thể dùng tên có tính định danh như **order-expiry-ord-1042**, group theo môi trường và payload chứa order ID cùng scheduled time. Khi đơn hàng bị hủy trước hạn, ứng dụng có thể disable hoặc delete schedule tương ứng. Handler vẫn phải đọc trạng thái đơn hàng trước khi thực hiện hành động, vì việc hủy schedule và lần invoke có thể xảy ra đồng thời.

Nếu tạo nhiều schedule một lần cho từng user hoặc từng resource, cần có chiến lược quản lý số lượng, dọn lịch đã hoàn tất, xử lý resource bị xóa và đối soát schedule mồ côi.

## 12. Tạo schedule bằng AWS CLI

Ví dụ tạo schedule chạy function tổng hợp báo cáo lúc 09:00 các ngày trong tuần theo giờ Việt Nam:

~~~bash
aws scheduler create-schedule \
  --name weekday-daily-summary \
  --group-name reporting-prod \
  --schedule-expression "cron(0 9 ? * MON-FRI *)" \
  --schedule-expression-timezone "Asia/Ho_Chi_Minh" \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target '{
    "Arn": "arn:aws:lambda:ap-southeast-1:123456789012:function:daily-summary:live",
    "RoleArn": "arn:aws:iam::123456789012:role/scheduler-invoke-daily-summary",
    "Input": "{\"jobType\":\"DAILY_SUMMARY\",\"scheduledTime\":\"<aws.scheduler.scheduled-time>\",\"executionId\":\"<aws.scheduler.execution-id>\",\"scheduleArn\":\"<aws.scheduler.schedule-arn>\"}",
    "LambdaParameters": {
      "InvocationType": "Event"
    },
    "RetryPolicy": {
      "MaximumEventAgeInSeconds": 3600,
      "MaximumRetryAttempts": 5
    },
    "DeadLetterConfig": {
      "Arn": "arn:aws:sqs:ap-southeast-1:123456789012:scheduled-target-dlq"
    }
  }' \
  --state ENABLED
~~~

Các ARN, account ID, Region, role và queue trong ví dụ là giá trị minh họa; cần thay bằng tài nguyên của môi trường triển khai. Scheduler execution role cần quyền invoke đúng alias và quyền gửi message tới DLQ. Nếu queue mã hóa bằng customer-managed KMS key, policy liên quan cũng cần cho phép thao tác cần thiết.

Với schedule một lần, có thể dùng:

~~~bash
aws scheduler create-schedule \
  --name expire-order-ord-1042 \
  --group-name orders-prod \
  --schedule-expression "at(2026-12-01T09:00:00)" \
  --schedule-expression-timezone "Asia/Ho_Chi_Minh" \
  --action-after-completion DELETE \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target file://target.json \
  --state ENABLED
~~~

Tách target JSON ra file giúp tránh lỗi escape khi payload phức tạp. Trước khi bật schedule, kiểm tra biểu thức, timezone, ARN, role, target payload và DLQ. Dùng môi trường thử nghiệm hoặc schedule ở tương lai gần để xác minh end-to-end.

## 13. Mô hình hóa bằng CloudFormation

Có thể quản lý schedule và group bằng CloudFormation. Ví dụ rút gọn:

~~~yaml
Resources:
  ReportingScheduleGroup:
    Type: AWS::Scheduler::ScheduleGroup
    Properties:
      Name: reporting-prod

  DailySummarySchedule:
    Type: AWS::Scheduler::Schedule
    Properties:
      Name: weekday-daily-summary
      GroupName: !Ref ReportingScheduleGroup
      State: ENABLED
      ScheduleExpression: cron(0 9 ? * MON-FRI *)
      ScheduleExpressionTimezone: Asia/Ho_Chi_Minh
      FlexibleTimeWindow:
        Mode: OFF
      Target:
        Arn: arn:aws:lambda:ap-southeast-1:123456789012:function:daily-summary:live
        RoleArn: !GetAtt SchedulerExecutionRole.Arn
        Input: '{"jobType":"DAILY_SUMMARY","scheduledTime":"<aws.scheduler.scheduled-time>"}'
        LambdaParameters:
          InvocationType: Event
        RetryPolicy:
          MaximumEventAgeInSeconds: 3600
          MaximumRetryAttempts: 5
        DeadLetterConfig:
          Arn: !GetAtt ScheduledTargetDLQ.Arn

  SchedulerExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: scheduler.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: InvokeDailySummary
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action:
                  - lambda:InvokeFunction
                Resource: arn:aws:lambda:ap-southeast-1:123456789012:function:daily-summary:live
              - Effect: Allow
                Action:
                  - sqs:SendMessage
                Resource: !GetAtt ScheduledTargetDLQ.Arn
~~~

Đây là ví dụ mô hình hóa, chưa phải template production hoàn chỉnh. Trust policy thực tế nên có điều kiện giới hạn source account và schedule group ARN. Cần khai báo queue DLQ, policy KMS nếu dùng khóa riêng, tagging và các thuộc tính bảo mật/vận hành cần thiết. Trong stack thực tế, dùng GetAtt hoặc Sub để tránh hardcode ARN và bảo đảm phụ thuộc tài nguyên đúng.

Khi cập nhật schedule qua API UpdateSchedule, cần gửi lại đầy đủ các thuộc tính mong muốn vì trường bị bỏ qua có thể được đặt về mặc định hoặc bị xóa theo semantics cập nhật. Với IaC, review diff trước khi deploy để tránh vô tình thay đổi timezone, target role hoặc trạng thái schedule.

## 14. Quản lý schedule: tạo, cập nhật, tạm dừng và xóa

Vòng đời schedule thường gồm:

1. Tạo schedule trong group.
2. Kiểm tra target, execution role, biểu thức và trạng thái.
3. Bật schedule.
4. Theo dõi invocation và kết quả.
5. Cập nhật biểu thức hoặc target khi nghiệp vụ thay đổi.
6. Tạm dừng bằng trạng thái DISABLED nếu cần bảo trì.
7. Xóa schedule khi không còn cần thiết.

Đối với lịch định kỳ, disable có thể hữu ích khi hệ thống đang bảo trì hoặc dependency không sẵn sàng. Tuy nhiên, disable không tự xử lý các lần chạy đã bỏ lỡ. Khi enable lại, hãy xác định có cần chạy bù các kỳ bị bỏ qua hay không. Scheduler không nên được coi là một hàng đợi lưu mọi lần chạy bị lỡ để tự động replay toàn bộ.

Đối với job theo lịch của từng khách hàng, khi resource nghiệp vụ bị xóa hoặc hủy, phải cập nhật schedule tương ứng. Nên lưu ARN hoặc định danh schedule trong metadata nghiệp vụ để có thể disable/delete chính xác. Việc dọn schedule cần idempotent vì thao tác delete có thể được thử lại.

## 15. Giới hạn, scale và thiết kế tránh burst

Một hệ thống có thể có rất nhiều schedule cùng chạy vào đầu giờ hoặc đầu ngày. Nếu tất cả cùng invoke một function hoặc cùng gọi database, target có thể bị throttling dù mỗi schedule riêng lẻ hợp lệ.

Các biện pháp:

- Bật flexible time window cho công việc không cần thời điểm chính xác.
- Phân tán phút chạy bằng cron khi nghiệp vụ cho phép.
- Đặt reserved concurrency phù hợp cho Lambda.
- Giới hạn concurrency của worker và connection pool.
- Đưa tác vụ nặng vào SQS hoặc workflow để hấp thụ tải.
- Dùng batch processing với giới hạn rõ ràng.
- Thiết kế idempotency cho duplicate invocation.
- Theo dõi target throttling và tuổi backlog.
- Không tạo schedule cho từng bản ghi nếu một schedule tổng hợp có thể quét dữ liệu đến hạn theo batch.

Nếu có hàng trăm nghìn bản ghi hết hạn, một schedule chạy mỗi phút và truy vấn index theo expiresAt có thể phù hợp hơn việc tạo một schedule cho mỗi bản ghi. Ngược lại, nếu mỗi khách hàng có một thời điểm thực hiện riêng và cần quản trị độc lập, schedule riêng có thể là lựa chọn hợp lý. Hãy cân nhắc số lượng schedule, chi phí, quota dịch vụ và khả năng dọn lịch.

## 16. Quan sát và xử lý sự cố

Cần theo dõi cả việc Scheduler giao target và việc function hoàn tất nghiệp vụ.

Ở phía Scheduler, quan sát các metric CloudWatch của namespace AWS/Scheduler, gồm số lần thử invoke, target error/throttling, invocation bị bỏ hoặc gửi DLQ theo metric dịch vụ cung cấp. Dùng CloudTrail để xem hoạt động quản trị như tạo, cập nhật, bật/tắt và xóa schedule.

Ở phía Lambda, theo dõi:

- Invocations, Errors, Duration và Throttles.
- Concurrent executions và timeout.
- Async event age, retry và destination/DLQ nếu dùng invocation bất đồng bộ.
- Log của handler với request ID, schedule ARN và scheduled time.
- Business metrics như số job hoàn tất, bỏ qua do duplicate, thất bại và chạy trễ.

Một số tình huống thường gặp:

| Triệu chứng | Nơi kiểm tra |
|---|---|
| Schedule không chạy | State, expression, timezone, start/end date, group và flexible window |
| Scheduler không invoke được Lambda | Execution role trust, lambda:InvokeFunction, ARN/alias, target policy và Region |
| Scheduler DLQ tăng | Target API throttling, permission, target availability và Scheduler retry policy |
| Lambda được invoke nhưng job thất bại | Lambda logs, function timeout, dependency, async retry/DLQ |
| Job chạy hai lần | Duplicate delivery, retry, idempotency key và thao tác claim state |
| Job chạy trễ | Flexible window, service delivery precision, throttling và concurrency |
| Schedule cũ vẫn tồn tại | ActionAfterCompletion, cleanup workflow và schedule group inventory |
| Schedule bật nhưng không có log | Kiểm tra metric Scheduler trước, sau đó Lambda invocation và quyền ghi log |

Log nên ghi scheduleArn, scheduledTime, executionId, jobType, kết quả idempotency và thời gian xử lý. Không ghi secret hoặc toàn bộ payload nếu có dữ liệu nhạy cảm.

## 17. Bảo mật và bảo vệ dữ liệu

Scheduler có thể truyền payload tới target và assume role để gọi API. Vì vậy, bảo mật cần được thiết kế ở cả dữ liệu lịch lẫn quyền thực thi.

- Dùng execution role riêng hoặc role theo nhóm target, với quyền tối thiểu.
- Giới hạn trust policy theo source account và schedule group khi phù hợp.
- Chỉ cho phép invoke function ARN hoặc alias cần thiết.
- Cấp sqs:SendMessage cho DLQ đúng queue; kiểm tra KMS policy nếu queue mã hóa.
- Không đưa password, token hoặc secret vào Input của schedule.
- Truyền định danh tham chiếu, để Lambda đọc secret qua Secrets Manager/Parameter Store bằng execution role riêng.
- Bật mã hóa dữ liệu schedule bằng customer-managed KMS key nếu yêu cầu kiểm soát khóa.
- Giới hạn principal được tạo, cập nhật, disable và delete schedule.
- Kiểm tra quyền ở function trước khi thực hiện side effect; payload không chứng minh caller hay tenant.
- Xóa hoặc rút ngắn vòng đời schedule và payload khi không còn cần thiết.

Schedule input có thể tồn tại trong cấu hình tài nguyên và xuất hiện trong công cụ quản trị hoặc audit. Chỉ đưa dữ liệu tối thiểu cần thiết vào payload.

## 18. Khi nào nên dùng Scheduler, queue delay hoặc workflow timer?

Không phải mọi tác vụ tương lai đều cần một schedule riêng.

| Nhu cầu | Cơ chế thường phù hợp |
|---|---|
| Một lần chạy vào thời điểm xác định | EventBridge Scheduler at |
| Lịch lặp theo giờ/ngày/tuần/tháng | EventBridge Scheduler cron |
| Chạy theo chu kỳ cố định | EventBridge Scheduler rate |
| Đợi một khoảng ngắn trước khi giao message | Queue delay hoặc message visibility phù hợp |
| Điều phối nhiều bước, retry và chờ lâu giữa các bước | AWS Step Functions với Wait state |
| Xử lý hàng loạt bản ghi đến hạn | Scheduler kích hoạt một sweeper function |
| Định tuyến event nghiệp vụ tới nhiều consumer | EventBridge event bus và rules |

Ví dụ, một đơn hàng cần hết hạn sau 30 phút có thể dùng schedule at riêng nếu cần một timer cho từng đơn. Nếu có hàng triệu đơn và mỗi phút có thể quét các đơn đến hạn theo index, một schedule định kỳ kích hoạt sweeper có thể đơn giản và rẻ hơn. Nếu quy trình có nhiều bước như chờ thanh toán, nhắc khách, hủy đơn và hoàn tồn kho, Step Functions có thể biểu diễn trạng thái và timer rõ hơn.

Đừng dùng Scheduler để thay thế queue cho tải công việc lớn cần buffering, hoặc thay thế workflow engine khi cần điều phối nhiều bước và trạng thái dài hạn.

## 19. Checklist thiết kế schedule production

Trước khi bật schedule, hãy kiểm tra:

1. Nhu cầu là chạy một lần, theo chu kỳ hay theo lịch cron?
2. Biểu thức at, rate hoặc cron có đúng cú pháp và ý nghĩa nghiệp vụ không?
3. Timezone có được chỉ định rõ không? Có ảnh hưởng DST không?
4. Flexible time window có phù hợp với độ trễ nghiệp vụ chấp nhận không?
5. Target ARN và invocation type có đúng không?
6. Scheduler execution role có trust policy và quyền tối thiểu không?
7. Lambda execution role có quyền tới database, S3 hoặc dependency cần thiết không?
8. Retry policy và Scheduler DLQ có được cấu hình không?
9. Nếu Lambda chạy bất đồng bộ, Lambda async retry và failure destination đã được kiểm tra chưa?
10. Handler có idempotent theo scheduled time và business key không?
11. Payload có chứa scheduled time và định danh cần thiết không?
12. Lịch một lần có ActionAfterCompletion phù hợp không?
13. Có quy trình disable, update, delete và dọn schedule mồ côi không?
14. Có kiểm tra quota, burst, concurrency và dependency budget không?
15. Có metric, alarm, log và CloudTrail để điều tra không?
16. Có kiểm thử duplicate delivery, target throttling, handler failure và replay DLQ không?
17. IaC có quản lý schedule group, schedule, role, DLQ và target không?

## Kết luận

EventBridge Scheduler giúp chạy Lambda hoặc dịch vụ AWS khác theo lịch một lần, rate hoặc cron mà không cần giữ một process sống để chờ thời điểm kích hoạt. Schedule xác định thời gian và target; flexible window phân tán tải; execution role cấp quyền gọi target; retry và DLQ xử lý lỗi giao target. Khi Lambda nhận event bất đồng bộ, retry và failure destination của Lambda là lớp riêng cần cấu hình và theo dõi.

Với Java function, hãy nhận payload có cấu trúc, dùng scheduled time để xác định kỳ nghiệp vụ, lưu trạng thái bền vững và bảo đảm idempotency theo schedule cùng thời điểm dự kiến. Chọn timezone rõ ràng, giới hạn concurrency, dọn schedule một lần sau khi hoàn tất và theo dõi cả Scheduler lẫn Lambda. Khi công việc có nhiều bước hoặc cần chờ dài, cân nhắc Step Functions; khi cần buffering và retry message, dùng queue. Chọn đúng tài nguyên theo hình dạng của công việc sẽ giúp lịch chạy dễ vận hành và kiểm soát chi phí hơn.

