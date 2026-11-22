# Quản lý version, alias và quyền gọi function Lambda

Khi triển khai ứng dụng Java trên AWS Lambda, việc cập nhật JAR hoặc cấu hình function có thể ảnh hưởng ngay đến những request tiếp theo nếu caller đang gọi function không kèm qualifier. Điều đó gây khó khăn khi cần phát hành có kiểm soát, thử nghiệm phiên bản mới, quay lại bản ổn định hoặc giới hạn ai được phép gọi function.

AWS Lambda cung cấp **published version** để đóng băng một bản function, **alias** để tạo tên ổn định trỏ đến version, và hai lớp chính sách IAM để kiểm soát quyền gọi. Ba cơ chế này giải quyết ba câu hỏi khác nhau: mã và cấu hình nào được chạy, caller gọi vào phiên bản nào, và principal nào được phép invoke.

Bài học này hướng dẫn quản lý vòng đời version và alias, định tuyến traffic, phân biệt quyền invoke với quyền thực thi, và cấu hình quyền tối thiểu cho Java Lambda function được gọi qua API Gateway hoặc dịch vụ AWS khác.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt $LATEST, published version và alias.
- Giải thích những thành phần được đóng băng khi publish version và những phụ thuộc vẫn có thể thay đổi.
- Dùng alias để định tuyến execution mới đến một version cụ thể.
- Hiểu weighted alias routing và cách dùng cho canary deployment.
- Phân biệt identity-based policy, resource-based policy và execution role.
- Cấp quyền invoke cho IAM principal hoặc AWS service theo nguyên tắc least privilege.
- Publish version, cập nhật alias và cấp quyền bằng AWS CLI hoặc Java SDK v2.
- Thiết kế rollout, rollback và kiểm tra quyền gọi function.

## 1. $LATEST, published version và alias

Một Lambda function có ba khái niệm cần phân biệt.

| Thành phần | Ý nghĩa | Có thể thay đổi? | ARN có dạng |
|---|---|---|---|
| $LATEST | Bản function đang được chỉnh sửa và cập nhật | Có | `...:function:order-handler` hoặc qualifier `:$LATEST` |
| Published version | Snapshot code và cấu hình tại thời điểm publish | Không | `...:function:order-handler:17` |
| Alias | Tên trỏ đến một published version, có thể cấu hình routing | Có | `...:function:order-handler:prod` |

**$LATEST** là bản làm việc của function. Khi upload code hoặc cập nhật cấu hình không kèm publish, bản này thay đổi. Caller invoke function ARN không có qualifier thường chạy $LATEST. Điều này thuận tiện khi phát triển nhưng khó kiểm soát nếu production cũng gọi ARN không qualifier.

**Published version** là một snapshot được đánh số. Ví dụ version 17 đại diện cho code và cấu hình tại thời điểm publish. Sau khi tạo, version đó không thể chỉnh sửa; muốn thay đổi phải cập nhật function rồi publish version mới.

**Alias** là một tên có thể thay đổi như dev, staging, prod hoặc candidate. Alias trỏ đến một version chính và có thể có cấu hình phân phối một phần traffic đến version thứ hai. Caller sử dụng alias ARN để không cần biết số version cụ thể.

~~~mermaid
flowchart TD
    A["Lambda function: order-handler"] --> B["$LATEST (mutable)"]
    A --> C["Version 16 (immutable)"]
    A --> D["Version 17 (immutable)"]
    A --> E["Version 18 (immutable)"]
    F["Alias dev"] --> C
    G["Alias prod"] --> D
    H["Alias canary"] --> D
    H -. "5% traffic" .-> E
~~~

Sơ đồ minh họa alias prod đang trỏ version 17, còn alias canary phân phối một phần traffic sang version 18. Alias là một con trỏ có thể cập nhật; published version là bản phát hành bất biến.

Alias chỉ trỏ đến published version; không thể trỏ trực tiếp đến `$LATEST`. Nếu cần môi trường phát triển dùng code mới nhất chưa publish, caller có thể invoke function không qualifier trong môi trường dev riêng.

### ARN và qualifier

Một function ARN cơ bản có dạng:

~~~text
arn:aws:lambda:ap-southeast-1:123456789012:function:order-handler
~~~

Các ARN có qualifier:

~~~text
arn:aws:lambda:ap-southeast-1:123456789012:function:order-handler:17
arn:aws:lambda:ap-southeast-1:123456789012:function:order-handler:prod
~~~

Qualifier là số version hoặc tên alias. Khi gọi ARN không qualifier, caller thường gọi $LATEST. Khi gọi ARN có version, caller gọi đúng version bất biến. Khi gọi ARN có alias, Lambda phân giải alias theo cấu hình hiện tại.

Hãy dùng ARN có alias cho các tích hợp cần một tên ổn định như production. Cách này giúp triển khai version mới bằng cách cập nhật alias mà không phải sửa cấu hình của mọi caller.

## 2. Publish một version

Khi code và cấu hình đã sẵn sàng, publish version để tạo một mốc phát hành có thể tham chiếu.

Có thể publish bằng AWS CLI:

~~~bash
aws lambda publish-version \
  --function-name order-handler \
  --description "Release 2026-11-17"
~~~

Lệnh trả về số version và ARN. Ví dụ, nếu version mới là 17, ARN có qualifier `:17`.

Có thể dùng Java AWS SDK v2:

~~~java
import software.amazon.awssdk.services.lambda.LambdaClient;
import software.amazon.awssdk.services.lambda.model.PublishVersionRequest;
import software.amazon.awssdk.services.lambda.model.PublishVersionResponse;

public final class LambdaVersionPublisher {
    private final LambdaClient lambda;

    public LambdaVersionPublisher(LambdaClient lambda) {
        this.lambda = lambda;
    }

    public String publish(
            String functionName,
            String expectedCodeSha256,
            String revisionId) {

        PublishVersionRequest request = PublishVersionRequest.builder()
                .functionName(functionName)
                .description("Release approved for production")
                .codeSha256(expectedCodeSha256)
                .revisionId(revisionId)
                .build();

        PublishVersionResponse response = lambda.publishVersion(request);
        return response.functionArn();
    }
}
~~~

Ví dụ truyền CodeSha256 và RevisionId để tránh publish nhầm nếu code hoặc cấu hình đã thay đổi sau bước kiểm tra. Trong pipeline, lấy các giá trị này từ kết quả đọc function configuration hoặc quá trình build/deploy tương ứng. Có thể bỏ điều kiện nếu quy trình không cần optimistic concurrency, nhưng nên giữ một bước xác minh artifact và cấu hình trước publish.

### Version đóng băng những gì?

Published version lưu code và phần lớn cấu hình function tại thời điểm publish, chẳng hạn runtime, handler, role ARN, memory, timeout, environment variables, layers, VPC configuration và các thiết lập function liên quan theo dịch vụ.

Tuy nhiên, published version không đóng băng toàn bộ hệ thống:

- Role ARN được lưu trong version, nhưng policy gắn với IAM role đó vẫn có thể được chỉnh sửa.
- Secret ARN hoặc tên secret trong environment variable có thể được đóng băng, nhưng giá trị secret trong Secrets Manager có thể thay đổi.
- Database schema, dữ liệu, queue, API bên ngoài và các dịch vụ mà function gọi không nằm trong snapshot.
- Resource-based policy và các cấu hình tích hợp có phạm vi riêng; cần kiểm tra chúng khi phát hành.
- Runtime do AWS quản lý có thể nhận các bản vá nền tảng theo chính sách runtime của dịch vụ.

Do đó, version bất biến giúp tái tạo code/config của function nhưng không tự biến toàn bộ môi trường phụ thuộc thành bất biến.

### Chỉ publish khi có thay đổi cần phát hành

Một function version mới có thể được publish khi code hoặc cấu hình đã thay đổi kể từ lần publish trước. Pipeline nên kiểm tra nội dung thay đổi và lưu số version, function ARN, code hash, commit/build ID cùng thời điểm phát hành vào deployment record.

Không dùng số version làm bằng chứng duy nhất rằng một artifact đã được kiểm thử. Hãy gắn version với build artifact và kết quả kiểm thử có thể truy vết.

## 3. Tạo và cập nhật alias

Alias giúp tách tên môi trường khỏi số version. Ví dụ alias prod có thể trỏ version 17 hôm nay và version 18 sau lần release tiếp theo.

Tạo alias bằng AWS CLI:

~~~bash
aws lambda create-alias \
  --function-name order-handler \
  --name prod \
  --function-version 17 \
  --description "Production traffic"
~~~

Cập nhật alias:

~~~bash
aws lambda update-alias \
  --function-name order-handler \
  --name prod \
  --function-version 18
~~~

Trong Java SDK v2:

~~~java
import software.amazon.awssdk.services.lambda.LambdaClient;
import software.amazon.awssdk.services.lambda.model.UpdateAliasRequest;
import software.amazon.awssdk.services.lambda.model.UpdateAliasResponse;

public final class LambdaAliasManager {
    private final LambdaClient lambda;

    public LambdaAliasManager(LambdaClient lambda) {
        this.lambda = lambda;
    }

    public String pointProductionTo(
            String functionName,
            String aliasName,
            String version) {

        UpdateAliasResponse response = lambda.updateAlias(
                UpdateAliasRequest.builder()
                        .functionName(functionName)
                        .name(aliasName)
                        .functionVersion(version)
                        .build());

        return response.aliasArn();
    }
}
~~~

Alias là cấu hình mutable. Hãy giới hạn quyền cập nhật alias cho deployment role và người chịu trách nhiệm phát hành. Runtime role của function thường không cần quyền `lambda:UpdateAlias`.

### Alias không thay đổi code

Khi cập nhật alias từ version 17 sang 18, Lambda không sửa version 17 hoặc version 18. Alias chỉ đổi nơi mà caller dùng alias sẽ được định tuyến. Caller gọi trực tiếp version ARN 17 vẫn chạy version 17; caller gọi $LATEST vẫn chạy bản mutable.

Vì vậy, cần thống nhất trong team rằng production caller sử dụng alias ARN. Nếu một caller dùng alias và caller khác gọi $LATEST, hai caller có thể chạy hai bản code khác nhau ngoài ý muốn.

## 4. Weighted alias routing và canary deployment

Alias có thể trỏ đến một version chính và phân phối một tỷ lệ invocation đến một version phụ. Đây là cách triển khai canary đơn giản: đưa một phần traffic sang bản mới, quan sát lỗi và latency, rồi tăng dần tỷ lệ hoặc quay về version cũ.

Ví dụ alias prod trỏ version 17, phân phối 5% invocation sang version 18:

~~~bash
aws lambda update-alias \
  --function-name order-handler \
  --name prod \
  --function-version 17 \
  --routing-config '{"AdditionalVersionWeights":{"18":0.05}}'
~~~

Tỷ lệ 0.05 là 5% cho version 18; phần traffic còn lại đi đến version chính 17. Weighted routing hỗ trợ một version chính và một version phụ trong cấu hình alias. Không thể khai báo tùy ý nhiều version phụ trong cùng cấu hình weighted alias.

Trong Java SDK v2:

~~~java
import java.util.Map;
import software.amazon.awssdk.services.lambda.LambdaClient;
import software.amazon.awssdk.services.lambda.model.AliasRoutingConfiguration;
import software.amazon.awssdk.services.lambda.model.UpdateAliasRequest;

public final class CanaryAliasManager {
    private final LambdaClient lambda;

    public CanaryAliasManager(LambdaClient lambda) {
        this.lambda = lambda;
    }

    public void sendFivePercentToCanary(
            String functionName,
            String aliasName,
            String stableVersion,
            String canaryVersion) {

        AliasRoutingConfiguration routing =
                AliasRoutingConfiguration.builder()
                        .additionalVersionWeights(
                                Map.of(canaryVersion, 0.05))
                        .build();

        lambda.updateAlias(UpdateAliasRequest.builder()
                .functionName(functionName)
                .name(aliasName)
                .functionVersion(stableVersion)
                .routingConfig(routing)
                .build());
    }
}
~~~

### Quy trình canary

1. Publish version mới sau khi build và kiểm thử.
2. Giữ alias prod trỏ version ổn định.
3. Cấu hình một tỷ lệ nhỏ traffic đến version mới.
4. Theo dõi error rate, duration, throttling, timeout và lỗi nghiệp vụ.
5. Tăng tỷ lệ theo từng bước nếu các chỉ số đạt ngưỡng.
6. Chuyển 100% traffic sang version mới khi đã đủ tin cậy.
7. Nếu có vấn đề, xóa weighted routing và trỏ alias về version ổn định.

Canary routing chỉ phân phối invocation đến version; nó không tự xác minh kết quả nghiệp vụ. Hãy dùng CloudWatch metrics, logs, tracing và metric nghiệp vụ để so sánh hai version.

Không mặc định mọi loại trigger có cùng semantics hoặc hỗ trợ mọi cách rollout. Đặc biệt với event source mapping, batch, retry và nguồn bất đồng bộ, hãy kiểm tra hành vi của tích hợp khi alias có weighted routing trước khi dùng cho production. Với workflow hoặc event cần giữ cùng version xuyên suốt nhiều bước, hãy truyền version/route đã chọn một cách có chủ đích thay vì để mỗi bước tự resolve alias ở thời điểm khác nhau.

### Rollback alias

Rollback traffic mới thường là cập nhật alias về version ổn định:

~~~bash
aws lambda update-alias \
  --function-name order-handler \
  --name prod \
  --function-version 17 \
  --routing-config '{}'
~~~

Lệnh này chuyển alias prod về version 17 và bỏ routing phụ. Nó không hoàn tác side effect mà version 18 đã thực hiện, cũng không đổi các invocation đã hoàn tất. Nếu version mới đã ghi dữ liệu hoặc gửi yêu cầu ra hệ thống ngoài, cần quy trình compensation hoặc đối soát nghiệp vụ riêng.

## 5. Quyền gọi function: hai hướng cần phân biệt

Khi một Lambda function được gọi, có hai câu hỏi về quyền:

1. **Caller có quyền invoke function không?**
2. **Sau khi chạy, function có quyền truy cập database, queue, object storage hoặc dịch vụ khác không?**

Đây là hai đường quyền khác nhau.

~~~mermaid
flowchart LR
    A["Caller: user / role / AWS service"] -->|"lambda:InvokeFunction"| B["Lambda function"]
    B -->|"Assume execution role"| C["IAM execution role"]
    C -->|"s3:GetObject / sqs:SendMessage / ... "| D["AWS resources"]
~~~

- Caller cần quyền gọi function thông qua identity-based policy hoặc resource-based policy thích hợp.
- Lambda assume execution role để chạy code. Trust policy cho phép service principal `lambda.amazonaws.com` assume role; permission policy trên role cho phép code truy cập các dịch vụ khác.
- Execution role không tự cấp quyền cho API Gateway, EventBridge hoặc user bên ngoài gọi function.
- Resource-based policy cho phép principal bên ngoài gọi function không tự cấp quyền cho code bên trong function đọc S3 hoặc ghi DynamoDB.

### Identity-based policy

Identity-based policy gắn với IAM user, group hoặc role của caller. Policy nêu action và resource mà principal được phép gọi.

Ví dụ cho một role chỉ được invoke alias prod:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:order-handler:prod"
    }
  ]
}
~~~

Gắn policy này vào IAM role mà ứng dụng hoặc người gọi sử dụng. Không cấp `lambda:*` nếu caller chỉ cần invoke một function cụ thể.

### Resource-based policy

Resource-based policy được gắn trực tiếp vào Lambda function, version hoặc alias. Policy cho phép một principal cụ thể, thường là AWS service hoặc account/role khác, gọi function.

Ví dụ, API Gateway cần quyền invoke Lambda. Có thể cấp quyền cho service principal `apigateway.amazonaws.com` và giới hạn bằng source ARN của API/stage/method/resource. Việc giới hạn source giúp tránh một API Gateway resource khác trong phạm vi principal đó gọi nhầm function.

## 6. Cấp quyền cho AWS service bằng AddPermission

Dùng AWS CLI để cấp quyền cho API Gateway gọi alias prod:

~~~bash
aws lambda add-permission \
  --function-name order-handler \
  --qualifier prod \
  --statement-id allow-orders-api-prod \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:ap-southeast-1:123456789012:api-id/prod/POST/orders"
~~~

Các tham số quan trọng:

| Tham số | Ý nghĩa |
|---|---|
| `--function-name` | Function được cấp quyền |
| `--qualifier prod` | Gắn permission vào alias prod |
| `--statement-id` | ID duy nhất của statement trong resource policy |
| `--action` | Action được cho phép, ở đây là `lambda:InvokeFunction` |
| `--principal` | Service hoặc principal được phép gọi |
| `--source-arn` | Giới hạn nguồn gọi, ví dụ API Gateway route cụ thể |

Nếu API Gateway gọi alias prod, integration URI phải trỏ đúng alias ARN. Cấp permission cho alias nhưng integration lại gọi unqualified function ARN có thể khiến lời gọi không khớp với policy hoặc chạy sai version dự kiến.

Có thể thêm source account khi phù hợp với dịch vụ tích hợp và mẫu policy để ràng buộc tài khoản nguồn. Hãy dùng ARN nguồn cụ thể nhất mà dịch vụ cung cấp, tránh wildcard rộng nếu không cần thiết.

### Java SDK v2: thêm resource permission

~~~java
import software.amazon.awssdk.services.lambda.LambdaClient;
import software.amazon.awssdk.services.lambda.model.AddPermissionRequest;

public final class LambdaPermissionManager {
    private final LambdaClient lambda;

    public LambdaPermissionManager(LambdaClient lambda) {
        this.lambda = lambda;
    }

    public void allowApiGateway(
            String functionName,
            String alias,
            String apiExecutionArn) {

        lambda.addPermission(AddPermissionRequest.builder()
                .functionName(functionName)
                .qualifier(alias)
                .statementId("allow-orders-api-prod")
                .action("lambda:InvokeFunction")
                .principal("apigateway.amazonaws.com")
                .sourceArn(apiExecutionArn)
                .build());
    }
}
~~~

Đoạn code cần được chạy bởi deployment role có quyền quản lý resource policy của Lambda. Không đặt thao tác AddPermission trong mỗi request handler; đây là cấu hình hạ tầng khi triển khai, không phải nghiệp vụ runtime.

## 7. Quyền gọi từ AWS service và event source mapping

Cách cấp quyền còn phụ thuộc dịch vụ nào kích hoạt function.

| Kiểu tích hợp | Cơ chế gọi | Quyền thường cần |
|---|---|---|
| API Gateway, S3 notification, SNS, EventBridge rule | Dịch vụ gửi invocation đến Lambda | Resource-based policy cho service principal, thường giới hạn source ARN/account |
| IAM user hoặc role gọi SDK | Caller chủ động gọi Lambda API | Identity-based policy; cross-account còn cần policy ở phía resource |
| SQS event source mapping | Lambda poll queue rồi invoke function | Execution role có quyền đọc/xóa message và đọc thuộc tính queue; cấu hình mapping trỏ function |
| Kinesis/DynamoDB Streams event source mapping | Lambda poll shard/stream | Execution role có quyền đọc stream và mô tả shard; mapping quản lý checkpoint |
| Function URL | Client gọi endpoint URL | Cấu hình AuthType và policy/action tương ứng với URL |

Với **push integration** như S3, SNS hoặc EventBridge, dịch vụ cần được phép invoke function; Lambda resource policy thường là nơi cấp quyền này.

Với **poll-based event source mapping** như SQS, Lambda service đọc queue bằng execution role của function rồi gọi handler. Role cần những quyền như `sqs:ReceiveMessage`, `sqs:DeleteMessage` và `sqs:GetQueueAttributes`; queue mã hóa bằng KMS có thể cần thêm quyền giải mã. Không nhầm quyền đọc queue của execution role với quyền invoke từ service principal.

### Function URL

Function URL có AuthType `AWS_IAM` hoặc `NONE`. Với `AWS_IAM`, caller phải ký request bằng AWS credentials và có quyền invoke phù hợp. Với `NONE`, endpoint có thể được gọi công khai theo resource policy. Function URL có action permission riêng như `lambda:InvokeFunctionUrl`; một số cấu hình còn yêu cầu `lambda:InvokeFunction` tương ứng. Hãy cấu hình theo AuthType và tài liệu hiện hành của Function URL, không sao chép nguyên policy của API Gateway.

Không chọn `NONE` chỉ để tránh cấu hình IAM. Nếu endpoint nhận dữ liệu nghiệp vụ hoặc thao tác ghi, cần lớp xác thực/ủy quyền ứng dụng phù hợp và kiểm soát nguồn gọi.

## 8. Execution role: quyền mà code Lambda sử dụng

Mỗi function cần một execution role. Trust policy cho phép Lambda service assume role. Ví dụ trust relationship cơ bản:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Permission policy trên role cấp quyền cho code. Ví dụ function chỉ cần ghi log và đọc object từ một bucket cụ thể:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/lambda/order-handler:*"
    },
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::orders-input/*"
    }
  ]
}
~~~

Đây là ví dụ policy minh họa; quyền CloudWatch Logs cụ thể còn phụ thuộc log group đã được tạo hay chưa và cách triển khai. Với production, có thể dùng policy managed phù hợp làm điểm khởi đầu rồi thu hẹp resource theo nhu cầu.

Không cấp quyền rộng như `s3:*` trên `*` nếu function chỉ đọc một prefix. Tách role giữa các function có nhiệm vụ khác nhau để một function bị xâm nhập không tự động có quyền trên mọi dữ liệu của ứng dụng.

## 9. Quyền cho alias và version

Lambda resource-based policy có thể gắn ở cấp function, version hoặc alias. Điều này quan trọng khi caller phải gọi một bản phát hành cụ thể.

Ví dụ:

- Alias prod trỏ version 17.
- API Gateway integration gọi ARN `:prod`.
- Resource policy gắn vào alias prod cho phép API Gateway invoke.
- Deployment role có quyền cập nhật alias.
- Runtime execution role có quyền truy cập database và log cần thiết.

Khi alias prod chuyển sang version 18, caller vẫn dùng cùng alias ARN. Hãy kiểm tra policy và tích hợp trên alias sau mỗi lần phát hành, đặc biệt nếu deployment tạo alias mới hoặc thay đổi tên alias.

Một policy gắn ở function không qualifier có phạm vi khác với policy gắn vào qualifier cụ thể. Không giả định permission trên $LATEST tự động áp dụng theo cách mong muốn cho alias/version. Hãy đọc resource policy của đúng ARN mà caller thực sự invoke và kiểm thử bằng principal thực tế.

### Cross-account invocation

Nếu một IAM role ở account A gọi Lambda trong account B, thường cần cả hai phía cho phép:

1. Identity-based policy ở account A cho phép role gọi ARN của function/alias ở account B.
2. Resource-based policy ở account B cho phép principal hoặc account A invoke function/alias đó.

Nếu một AWS service ở account khác gọi function, resource policy phải giới hạn principal và nguồn gọi phù hợp. Tránh cấp quyền cho toàn bộ account hoặc principal rộng khi chỉ một role/service cụ thể cần truy cập.

## 10. Least privilege và tránh confused deputy

Khi cho phép AWS service invoke function, chỉ ghi principal như `events.amazonaws.com` hoặc `apigateway.amazonaws.com` có thể quá rộng nếu không giới hạn nguồn. Một service principal có thể đại diện cho nhiều tài nguyên trong nhiều tài khoản.

Dùng `SourceArn` để ràng buộc tài nguyên nguồn cụ thể, và `SourceAccount` khi mẫu tích hợp hỗ trợ và cần ràng buộc tài khoản sở hữu nguồn. Điều này giúp giảm nguy cơ confused deputy: một tài nguyên khác lợi dụng quyền của service để gọi function ngoài ý muốn.

Các nguyên tắc nên áp dụng:

- Cấp quyền cho đúng principal, đúng action và đúng function qualifier.
- Giới hạn source ARN/account cho service principal khi có thể.
- Không dùng wildcard cho toàn bộ API, bucket hoặc event bus nếu chỉ một nguồn cần gọi.
- Tách quyền deploy/publish/update alias khỏi quyền runtime của function.
- Rà soát resource policy và IAM policy định kỳ.
- Thu hồi statement cũ khi trigger hoặc integration bị xóa.
- Kiểm tra quyền qua IAM policy simulator hoặc thử invoke từ đúng principal trong môi trường kiểm thử.

## 11. Quy trình phát hành version và alias

Một pipeline phát hành có thể theo trình tự:

1. Build JAR và lưu artifact bất biến theo commit/build ID.
2. Cập nhật code và cấu hình $LATEST trong môi trường đích.
3. Chạy kiểm thử smoke hoặc integration trên $LATEST/staging.
4. Publish version sau khi xác minh code hash và cấu hình.
5. Cập nhật alias staging sang version mới và chạy kiểm thử tích hợp.
6. Cập nhật alias canary/prod theo chiến lược traffic đã chọn.
7. Theo dõi metrics và logs theo version.
8. Promote 100% traffic hoặc rollback alias.
9. Ghi deployment record: version, alias, artifact hash, commit, thời điểm, người/role phát hành và kết quả.
10. Chỉ xóa version cũ khi chắc chắn không còn alias, caller, event source mapping hoặc quy trình rollback cần dùng.

~~~mermaid
flowchart TD
    A["Build Java artifact"] --> B["Update $LATEST"]
    B --> C["Smoke test"]
    C --> D["Publish version N"]
    D --> E["Move staging alias"]
    E --> F["Integration test"]
    F --> G["Canary on prod alias"]
    G --> H{"Metrics acceptable?"}
    H -->|Yes| I["Promote 100% to N"]
    H -->|No| J["Rollback alias"]
    I --> K["Record release and retain prior version"]
~~~

### Kiểm tra quyền sau triển khai

Một release có thể chạy đúng khi developer test bằng role rộng nhưng thất bại khi API Gateway hoặc EventBridge invoke bằng service principal. Hãy kiểm tra cả hai hướng:

- Caller có thể invoke đúng alias ARN không?
- Resource policy có principal và source ARN đúng không?
- Function có thể assume execution role không?
- Execution role có quyền đọc/ghi resource cần thiết không?
- KMS key policy, VPC endpoint policy hoặc bucket policy có chặn request không?
- Trigger/event source mapping đang trỏ đúng function ARN/alias không?

Đừng chỉ test function bằng console test event; test đó không chứng minh integration principal trong production đã có quyền gọi.

## 12. Tình huống thực tế: API Gateway gọi Java Lambda qua alias prod

Giả sử một API `POST /orders` gọi Java Lambda `order-handler`. Production alias prod trỏ version 17.

Cấu hình nên có:

- API Gateway integration URI trỏ alias ARN của order-handler.
- Lambda resource policy cho phép principal `apigateway.amazonaws.com` invoke alias prod từ đúng API, stage, method và resource.
- Function execution role cho phép ghi log và truy cập đúng bảng/database cần thiết.
- Deployment role được phép update function code/config, publish version, update alias và add/remove permission.
- Caller bên ngoài được xác thực ở API Gateway theo cơ chế của API.

Khi phát hành version 18:

1. Upload JAR mới lên $LATEST và cập nhật cấu hình.
2. Kiểm thử function trong staging.
3. Publish version 18.
4. Giữ API Gateway gọi alias prod.
5. Chuyển alias prod sang version 18 hoặc bật weighted routing nếu trigger phù hợp.
6. Theo dõi error rate, latency, throttling và lỗi nghiệp vụ.
7. Nếu có lỗi, trỏ alias về version 17.
8. Giữ version 18 để điều tra; không xóa ngay sau rollback.

Caller vẫn gửi request đến cùng API URL. API Gateway tiếp tục invoke cùng alias ARN; alias quyết định version được chạy.

## 13. Checklist quản lý version, alias và quyền gọi

- [ ] Production không vô tình gọi $LATEST khi cần release ổn định.
- [ ] Mỗi release đã publish thành version bất biến và gắn với artifact/build ID.
- [ ] Alias prod/staging/canary trỏ đến version đã kiểm thử.
- [ ] Caller sử dụng đúng alias ARN hoặc version ARN theo thiết kế.
- [ ] Weighted routing chỉ bật khi trigger và integration hỗ trợ semantics đã kiểm chứng.
- [ ] Rollback alias đã được diễn tập và hiểu rõ không đảo ngược side effect.
- [ ] Identity-based policy cấp quyền invoke cho đúng caller và function ARN.
- [ ] Resource-based policy cấp quyền cho đúng service principal và source ARN/account.
- [ ] Execution role có trust policy cho Lambda và permission policy tối thiểu.
- [ ] Không nhầm quyền invoke với quyền code truy cập AWS resource.
- [ ] SQS/stream event source mapping có quyền đọc nguồn trong execution role.
- [ ] Function URL dùng AuthType và permission action phù hợp.
- [ ] Cross-account invocation có policy cho phép ở cả hai phía khi cần.
- [ ] Deployment role tách biệt với runtime execution role.
- [ ] Resource policy cũ được rà soát khi xóa integration hoặc trigger.
- [ ] Đã kiểm thử invoke từ principal thật và xác minh log/metrics theo version.

## Tự kiểm tra

1. Khi caller invoke function ARN không qualifier, Lambda chạy bản nào? Vì sao điều này có thể nguy hiểm trong production?
2. Published version đóng băng những cấu hình nào và những phụ thuộc nào vẫn có thể thay đổi?
3. Alias khác published version như thế nào?
4. Weighted alias routing có thể hỗ trợ canary deployment ra sao?
5. Identity-based policy và resource-based policy khác nhau ở vị trí gắn và cách xác định principal thế nào?
6. Execution role có cấp quyền cho API Gateway invoke function không? Giải thích hai hướng quyền.
7. Vì sao permission cho service principal nên giới hạn bằng SourceArn và có thể cả SourceAccount?
8. Với SQS event source mapping, vì sao execution role cần quyền đọc queue?
9. Khi rollback alias về version cũ, những side effect nào vẫn cần được xử lý riêng?

Quản lý Lambda version và alias giúp kiểm soát chính xác bản code được chạy qua từng giai đoạn phát hành. IAM identity policy, Lambda resource policy và execution role bảo vệ các hướng truy cập khác nhau. Khi caller dùng alias ổn định, version được publish bất biến, quyền được giới hạn theo principal và nguồn gọi, đội phát triển có thể triển khai Java function theo từng bước và khôi phục có kiểm soát.

