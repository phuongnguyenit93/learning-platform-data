# Parallel, Map và điều phối xử lý dữ liệu hàng loạt

Một hệ thống bán hàng có thể cần **kiểm tra tồn kho, tính phí vận chuyển và đánh giá rủi ro** cùng lúc trước khi xác nhận đơn hàng. Một hệ thống phân tích dữ liệu lại cần xử lý **hàng triệu dòng CSV hoặc hàng nghìn object S3** theo từng phần, ghi kết quả và thử lại những phần thất bại. Cả hai tình huống đều cần thực thi song song, nhưng quy mô, cách truyền dữ liệu và chiến lược lỗi rất khác nhau.

**AWS Step Functions** là dịch vụ điều phối workflow theo **Amazon States Language (ASL)**. Trong bài này, ba cơ chế cần phân biệt là:

- **Parallel state:** chạy **một số nhánh workflow độc lập**, rồi đợi các nhánh hoàn tất để tổng hợp kết quả.
- **Map state – Inline:** lặp một tập bước trên **mỗi phần tử của một JSON array**, với concurrency giới hạn và lịch sử thực thi chung với parent workflow.
- **Map state – Distributed:** phân rã tập dữ liệu lớn thành **child workflow executions**, có khả năng đọc dữ liệu từ S3, batch items, xuất kết quả ra S3 và thiết lập ngưỡng lỗi chấp nhận.

Bài thuộc chương **Sự kiện và điều phối** của mô-đun **CLOUD_PROVIDERS_AWS**. Người học kết nối Step Functions với Region/AZ, IAM, VPC, Lambda, ECS, S3, database và các dịch vụ tích hợp để thiết kế hệ thống an toàn, giám sát được, có khả năng phục hồi và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt nhu cầu **chạy nhiều nhánh khác nhau** với **xử lý từng item trong cùng một tập dữ liệu**.
2. Viết **ASL Parallel** và hiểu input fan-out, output array, thứ tự kết quả, Retry/Catch.
3. Viết **Inline Map** với **ItemsPath, ItemSelector, ItemProcessor, MaxConcurrency** và ResultPath.
4. Thiết kế **Distributed Map** dùng **ItemReader, ItemBatcher, ResultWriter**, child workflow và **Map Run**.
5. Hiểu các ràng buộc **256 KiB payload**, **25.000 history events**, concurrency **40** và **10.000**, cùng throttling thực tế.
6. Chọn **Standard/Express** cho workflow mẹ/con và ước lượng tác động tới semantics, log và chi phí.
7. Thiết kế **retry, backoff, failure thresholds, idempotency, redrive và checkpoint**.
8. Cấu hình IAM, S3/KMS, CloudWatch, theo dõi Map Run và xử lý lỗi production.
9. Vận dụng trong luồng ETL, xử lý ảnh, nhập catalog, kiểm soát ngân sách và batch report.

## 2. Bức tranh kiến trúc: fan-out và fan-in

~~~mermaid
flowchart TD
    EVENT["EventBridge / API / Schedule"] --> SF["AWS Step Functions<br/>Standard workflow"]
    SF --> CHOICE{"Cần kiểu song song nào?"}
    CHOICE -->|"Nhiều chức năng khác nhau"| PAR["Parallel<br/>Kiểm tra kho + giá + rủi ro"]
    CHOICE -->|"Mảng JSON nhỏ"| INLINE["Inline Map<br/>Xử lý từng item"]
    CHOICE -->|"Dataset lớn / S3"| DIST["Distributed Map<br/>Map Run"]
    PAR --> JOIN["Fan-in / tổng hợp kết quả"]
    INLINE --> JOIN
    DIST --> JOIN
    DIST --> S3["S3 ItemReader / ResultWriter"]
    INLINE --> L["Lambda / ECS / AWS SDK integrations"]
    PAR --> L
    DIST --> L
    JOIN --> DB["S3 / DynamoDB / RDS / notifications"]
~~~

**Fan-out** là tách công việc thành nhiều nhánh/lượt chạy. **Fan-in** là chờ và tổng hợp kết quả khi phần việc liên quan đã hoàn tất. Điều phối không mặc nhiên biến một tác vụ tuần tự thành tác vụ song song an toàn: phải xem **phụ thuộc dữ liệu**, **thứ tự thao tác**, **khả năng xử lý đồng thời của downstream** và **tính idempotent** của side effects.

| Bài toán | Lựa chọn khởi đầu | Lý do |
|---|---|---|
| Cùng lúc gọi kiểm tra tồn kho, khuyến mãi, fraud | **Parallel** | Ba nhánh logic khác nhau, số lượng nhánh cố định |
| Duyệt 20 items trong một đơn hàng | **Inline Map** | Mảng đầu vào nhỏ, cùng bước xử lý cho mỗi item |
| Chấm điểm 500.000 records CSV trên S3 | **Distributed Map** | Dataset lớn, concurrency và history tách biệt |
| Một công việc phải làm bước A rồi B rồi C | **Task nối tiếp** | Có phụ thuộc, không nên chạy song song |
| Một sự kiện được gửi cho nhiều hệ thống không cần chờ tổng hợp | **SNS/EventBridge fan-out** | Pub/sub có thể hợp hơn điều phối fan-in |
| Đẩy công việc đến consumer có backpressure dài hạn | **SQS + consumers**, có thể kết hợp Step Functions | Queue buffering phù hợp hơn mở vô hạn workflow đồng thời |

### 2.1. Step Functions không phải nơi chạy tác vụ CPU nặng

Step Functions giữ **trạng thái điều phối**, không trực tiếp thay Lambda, ECS, AWS Batch hay Amazon EMR. Một state **Task** gọi dịch vụ làm việc; chi phí và giới hạn của task worker vẫn tồn tại. Với xử lý video/data nặng, Step Functions phối hợp **ECS/Batch/EMR/Glue** và chờ kết quả theo loại integration hỗ trợ.

## 3. Parallel state: chạy các nhánh độc lập

Một **Parallel** gồm danh sách **Branches**; mỗi branch là một state machine con với **StartAt** và **States** riêng. Các branch nhận **cùng input của Parallel** (sau khi áp dụng các phép biến đổi input phù hợp), bắt đầu chạy đồng thời trong khả năng dịch vụ, và Parallel đợi tất cả kết thúc thành công.

~~~mermaid
flowchart LR
    INPUT["Order input"] --> PAR["Parallel"]
    PAR --> A["Validate schema"]
    PAR --> B["Check inventory"]
    PAR --> C["Calculate shipping"]
    A --> JOIN["Result array<br/>[A, B, C]"]
    B --> JOIN
    C --> JOIN
    JOIN --> NEXT["Authorize payment"]
~~~

**Các nhánh độc lập về state transitions:** branch A không thể tham chiếu trực tiếp tên state bên trong branch B; dữ liệu cần chia sẻ giữa branches phải được truyền từ input chung hoặc thông qua hệ thống lưu trữ/đồng bộ phù hợp. Không nên dùng database shared state mơ hồ rồi cho rằng Parallel sẽ bảo đảm transaction isolation.

### 3.1. Kết quả Parallel là array theo thứ tự branch

Nếu branch A trả:

~~~json
{"check":"schema","ok":true}
~~~

Và branch B trả:

~~~json
{"check":"stock","available":true}
~~~

Output mặc định của Parallel là:

~~~json
[
  {"check":"schema","ok":true},
  {"check":"stock","available":true}
]
~~~

Thứ tự phần tử theo **thứ tự khai báo branch**, **không phải** thứ tự branch hoàn thành. Nếu cần gắn nhãn rõ kết quả, để mỗi branch trả object có tên hoặc dùng **ResultSelector/ResultPath**. Đừng suy rằng một branch hoàn thành trước thì output sẽ đứng trước.

### 3.2. ASL hoàn chỉnh: Parallel không cần tài nguyên AWS phụ

Ví dụ này dùng **Pass** states để minh họa fan-out/fan-in mà không cần Lambda thật:

~~~json
{
  "Comment": "Run independent checks in parallel",
  "StartAt": "CheckOrder",
  "States": {
    "CheckOrder": {
      "Type": "Parallel",
      "Branches": [
        {
          "StartAt": "ValidateSchema",
          "States": {
            "ValidateSchema": {
              "Type": "Pass",
              "Result": {"check": "schema", "ok": true},
              "End": true
            }
          }
        },
        {
          "StartAt": "CheckStock",
          "States": {
            "CheckStock": {
              "Type": "Pass",
              "Result": {"check": "stock", "available": true},
              "End": true
            }
          }
        }
      ],
      "ResultPath": "$.checks",
      "Next": "BuildResponse"
    },
    "BuildResponse": {
      "Type": "Pass",
      "Parameters": {
        "orderId.$": "$.orderId",
        "checks.$": "$.checks"
      },
      "End": true
    }
  }
}
~~~

Input minh họa:

~~~json
{"orderId":"o-101"}
~~~

Output là một object gồm **orderId** và **checks** array. **ResultPath = $.checks** giữ input gốc và chèn kết quả Parallel; nếu không đặt ResultPath, mặc định output state có thể thay thế input bằng array kết quả. **Parameters** trong Pass state trên dùng JSONPath để chọn trường; các ví dụ trong bài dùng ASL theo **JSONPath** để nhất quán.

### 3.3. Cùng input nhưng kết quả độc lập

| Thuộc tính | Parallel | Hậu quả thiết kế |
|---|---|---|
| **Branches** | Những workflows độc lập chạy song song | Branch không thể Next sang state ở branch khác |
| **Input** | Mỗi branch nhận bản dữ liệu phù hợp của input Parallel | Không kỳ vọng mutation trực tiếp sang branch khác |
| **Output** | Array kết quả theo thứ tự branch | Cần map đúng theo tên/nhãn |
| **Completion** | Chờ tất cả nhánh thành công | Nhánh chậm nhất làm fan-in chờ |
| **Failure** | Một branch lỗi chưa được xử lý làm Parallel lỗi | Thiết kế Retry/Catch và side effect idempotent |

### 3.4. Nếu một nhánh lỗi thì sao?

Khi branch thất bại chưa được xử lý, **Parallel state thất bại và Step Functions ngừng các branch còn lại ở mức workflow**. Nhưng **Lambda đã được invoke có thể vẫn tiếp tục chạy**; công việc external ở ECS, API hoặc database không mặc nhiên được rollback/kill. Đây là điểm quan trọng với những nhánh ghi dữ liệu hay phát hành hóa đơn.

Có hai chiến lược:

- **All-or-nothing về điều phối:** để lỗi lan ra Parallel, rồi Catch/compensate ở mức workflow sau khi xem xét side effects.
- **Best effort:** mỗi branch tự Catch lỗi thành kết quả có cấu trúc như **{"ok":false,"error":...}**, để các nhánh còn lại kết thúc và parent đánh giá kết quả.

**Retry tại cấp Parallel** có thể chạy lại cả những branch đã thành công trước đó. Tránh retry tổng thể không kiểm soát khi branch thực hiện chuyển tiền, ghi database hoặc gửi notification. Ưu tiên retry có giới hạn ở Task thích hợp và **idempotency keys**.

## 4. Inline Map: một logic áp dụng cho nhiều phần tử

Khi có một JSON array, **Map** chạy **ItemProcessor** cho từng phần tử. **Inline Map** mặc định chạy iterations trong **cùng execution history** của parent; theo AWS, hỗ trợ tối đa **40 concurrent iterations**. Với lượng dữ liệu vừa phải và input nhỏ, Inline đơn giản hơn Distributed Map.

~~~mermaid
flowchart LR
    INPUT["Input<br/>items:[A,B,C,D]"] --> MAP["Inline Map<br/>MaxConcurrency=2"]
    MAP --> I1["Item A → workflow"]
    MAP --> I2["Item B → workflow"]
    I1 --> I3["Item C → workflow"]
    I2 --> I4["Item D → workflow"]
    I3 --> OUT["Results array"]
    I4 --> OUT
~~~

### 4.1. Các trường ASL quan trọng

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| **Type: Map** | State lặp qua items | Map |
| **ItemsPath** | JSONPath đến array đầu vào (JSONPath workflows) | **$.items** |
| **ItemSelector** | Tạo input riêng cho mỗi iteration, lấy cả context | Current item, index, batchId |
| **ItemProcessor** | Định nghĩa states chạy cho từng item | Validate → Transform → Store |
| **ProcessorConfig.Mode: INLINE** | Dùng Inline Map | Không tạo child workflows độc lập |
| **MaxConcurrency** | Số iterations được phép đồng thời | 5, 10 hoặc 0 |
| **ResultPath** | Nơi kết quả Map được gắn vào input | **$.processed** |
| **Retry / Catch** | Phản ứng khi Map/iterations lỗi | Retry có giới hạn |

**MaxConcurrency = 0** nghĩa là Map không đặt giới hạn riêng và chạy đồng thời trong khả năng dịch vụ (Inline vẫn tối đa 40). **MaxConcurrency = 1** khiến items được thực thi từng lượt theo thứ tự, hữu ích khi cần giới hạn tải hoặc thứ tự; **không đồng nghĩa exactly-once business processing**.

### 4.2. ASL hoàn chỉnh: Inline Map với ItemSelector

~~~json
{
  "Comment": "Illustrate an Inline Map without external services",
  "StartAt": "ProcessItems",
  "States": {
    "ProcessItems": {
      "Type": "Map",
      "ItemsPath": "$.items",
      "MaxConcurrency": 5,
      "ItemSelector": {
        "item.$": "$$.Map.Item.Value",
        "index.$": "$$.Map.Item.Index",
        "batchId.$": "$.batchId"
      },
      "ItemProcessor": {
        "ProcessorConfig": {"Mode": "INLINE"},
        "StartAt": "Transform",
        "States": {
          "Transform": {
            "Type": "Pass",
            "Parameters": {
              "itemId.$": "$.item.id",
              "sourceIndex.$": "$.index",
              "status": "SIMULATED"
            },
            "End": true
          }
        }
      },
      "ResultPath": "$.processed",
      "End": true
    }
  }
}
~~~

Input mẫu:

~~~json
{
  "batchId": "batch-2026-11-20",
  "items": [
    {"id":"a1"},
    {"id":"a2"},
    {"id":"a3"}
  ]
}
~~~

Map trả output gồm input gốc và **processed** array. Mỗi item cho ra object **itemId, sourceIndex, status**. **$$.Map.Item.Index/Value** đọc từ **Context object của Map**; khai báo chúng trong **ItemSelector** để truyền vào iteration. Đây là ví dụ không thực hiện thao tác bên ngoài, thuận tiện kiểm tra cấu trúc ASL trước khi thay Task thật.

### 4.3. Inline Map có những giới hạn nào?

- Input là **JSON array** nằm trong state input; một item dataset quá lớn phải đặt ở S3 rồi cân nhắc Distributed Map.
- State input/output tối đa **256 KiB** theo quota chung Step Functions.
- Mọi event trong iterations góp vào lịch sử parent workflow; Standard executions có giới hạn **25.000 history events**.
- Một iteration chưa được xử lý lỗi có thể làm **toàn Map thất bại**, các iterations khác bị dừng ở mức workflow.
- MaxConcurrency không thay IAM permissions hoặc quota Lambda/DynamoDB/S3.

**Không kết luận 100 items là luôn an toàn với Inline**: nếu mỗi item qua 20 Task states và retry nhiều lần, số event history tăng rất nhanh. Ngược lại, 100 items chỉ qua một Pass nhẹ có thể phù hợp. Phải ước lượng **history events và output size**, không chỉ số item.

## 5. So sánh Parallel, Inline Map và Distributed Map

| Tiêu chí | Parallel | Inline Map | Distributed Map |
|---|---|---|---|
| **Mục đích** | Chạy nhiều nhánh **khác logic** | Lặp **một workflow** trên các items | Xử lý dataset lớn thành nhiều child executions |
| **Đầu vào** | Input dùng chung cho branches | JSON array trong state input | JSON array/object hoặc datasets trên S3 |
| **Đơn vị đồng thời** | Branch | Inline iteration | Child workflow execution |
| **Concurrency** | Số branches cấu hình, bị giới hạn bởi quota/tải | Tối đa **40** | Tối đa **10.000** child executions/Map Run |
| **Lịch sử** | Chung với parent | Chung với parent | Tách child histories khỏi parent |
| **Payload** | Giới hạn state/execution **256 KiB** | **256 KiB**, có thể lớn vì output array | Có thể đọc dataset S3 lớn; mỗi child input/output vẫn chịu quota |
| **Input S3 tích hợp** | Không có ItemReader | Không có ItemReader | **ItemReader** theo format được hỗ trợ |
| **Batch items** | Tự thiết kế ở branch | Không phải tính năng ItemBatcher Distributed | **ItemBatcher** |
| **Export results** | Tự gọi Task lưu S3 | Tự gọi Task lưu S3 | **ResultWriter** hỗ trợ S3 |
| **Failure tolerance per item** | Tùy Catch ở branches | Tùy Catch trong iterations | Có **ToleratedFailureCount/Percentage** |
| **Loại parent workflow** | Standard/Express theo khả năng | Standard/Express theo khả năng | **Standard parent**; child **Standard/Express** |
| **Phù hợp** | 3–5 kiểm tra độc lập | Một vài đến vài chục items | Hàng nghìn/hàng triệu items tùy kích thước/quota |

**Giới hạn 10.000 là mức đồng thời tối đa, không phải mặc định nên cấu hình.** Một job có 10.000 child invocations cùng gọi RDS có thể làm database bị nghẽn. Trong vận hành, đặt **MaxConcurrency dựa trên downstream capacity** và tăng dần sau benchmark.

### 5.1. Cây quyết định đơn giản

~~~mermaid
flowchart TD
    START["Có công việc song song?"] --> N{"Các nhánh có cùng workflow<br/>cho từng item?"}
    N -->|"Không"| PAR["Parallel<br/>Fan-out theo chức năng"]
    N -->|"Có"| BIG{"Dataset > 256 KiB,<br/>history lớn hoặc cần >40?"}
    BIG -->|"Không"| IN["Inline Map"]
    BIG -->|"Có"| DIS["Distributed Map<br/>Standard parent"]
    DIS --> LIM["Đặt MaxConcurrency,<br/>IAM, ItemReader/ResultWriter"]
    IN --> SAFETY["Retry/idempotency +<br/>output limits"]
    PAR --> SAFETY
    LIM --> SAFETY
~~~

## 6. Distributed Map: Map Run và child workflows

**Distributed Map** hoạt động trong **Standard parent workflow**. Nó tạo một **Map Run** có ARN và trạng thái riêng, đọc datasets (JSON array/objects hoặc S3), rồi điều phối **child workflow executions**. Mỗi child có lịch sử execution riêng; parent không ghi toàn bộ events xử lý của từng item như Inline Map.

~~~mermaid
flowchart TB
    EVENT["Schedule / API / EventBridge"] --> PARENT["Standard parent state machine"]
    PARENT --> MAP["Distributed Map / Map Run"]
    S3IN["S3 CSV / JSON / JSONL / Parquet<br/>object list / inventory / manifest"] --> READER["ItemReader"]
    READER --> BATCH["ItemSelector + ItemBatcher"]
    BATCH --> MAP
    MAP --> C1["Child workflow #1<br/>Standard hoặc Express"]
    MAP --> C2["Child workflow #2"]
    MAP --> CN["Child workflow #N"]
    C1 --> WORKER["Lambda / ECS / Batch"]
    C2 --> WORKER
    CN --> WORKER
    C1 --> WRITER["ResultWriter"]
    C2 --> WRITER
    CN --> WRITER
    WRITER --> S3OUT["S3 status / output / failure files"]
    MAP --> PARENT
~~~

### 6.1. Mối quan hệ parent, Map Run và child execution

| Đối tượng | Vai trò | Quan sát bằng gì? |
|---|---|---|
| **Parent execution** | Workflow điều phối toàn bộ batch job | DescribeExecution và execution graph |
| **Map Run** | Đại diện cho một lần chạy Distributed Map; theo dõi tiến độ/tỷ lệ lỗi | DescribeMapRun, ListMapRuns, Map Run metrics |
| **Child execution** | Xử lý một item hoặc một batch | Child execution ARN, trạng thái và logs |
| **Worker** | Lambda/ECS/Batch thực sự tính toán | Service metrics, traces, logs và IAM riêng |
| **S3 input/output** | Dữ liệu lớn và kết quả | S3 object version, bucket policy, KMS và lifecycle |

**Distributed Map không tự mở rộng vô hạn.** AWS Step Functions có hard quota **1.000 open Map Runs** và tối đa **10.000 child executions đồng thời trong một Map Run** theo tài liệu tại thời điểm viết. Việc dispatch các child workflows còn bị giới hạn bởi throughput API/Region và capacity thực tế; số child đang chạy có thể thấp hơn MaxConcurrency dù job có nhiều items.

### 6.2. Standard hay Express cho child?

| Child execution type | Tính chất phù hợp | Lưu ý |
|---|---|---|
| **STANDARD** | Tác vụ có workflow dài, cần lịch sử chi tiết và điều phối chịu lỗi cao | Phí state transitions, execution histories độc lập |
| **EXPRESS** | Tác vụ ngắn, số lượng lớn, chi phí/throughput cần tối ưu | Giới hạn thời gian **5 phút**, semantics at-least-once ở asynchronous Express, log/monitoring khác Standard |

**Parent chứa Distributed Map bắt buộc là Standard**, nhưng **ItemProcessor.ProcessorConfig.ExecutionType** có thể là **STANDARD** hoặc **EXPRESS** theo tính năng AWS hỗ trợ. Express child không sử dụng được một số service integration patterns như **.sync** hoặc callback **.waitForTaskToken**. Không chọn Express nếu mỗi item cần chờ job hàng giờ hoặc callback lâu.

### 6.3. Tại sao cần Map Run thay vì tự bắn hàng nghìn Lambda?

- Step Functions có **tập trung trạng thái và số liệu tiến độ** của toàn bộ job.
- Có ngưỡng **tolerated failures** và cơ chế redrive theo điều kiện hỗ trợ.
- Có thể dùng **ItemReader** đọc S3 dataset, **ItemBatcher** gom items và **ResultWriter** lưu kết quả.
- Có **MaxConcurrency** để hạn chế tải cùng lúc.
- Mỗi child có scope riêng, dễ tìm item lỗi hơn việc một Lambda tự tạo 10.000 requests không có tracking.

Tuy nhiên, nếu đầu vào đến liên tục và cần buffering/backpressure dài hạn, **SQS + Lambda/ECS consumers** hoặc AWS Batch có thể phù hợp hơn một Distributed Map được khởi động cho mọi event nhỏ. Lựa chọn theo **độ trễ, traffic pattern, retry semantics, chi phí và vận hành**.

## 7. ASL hoàn chỉnh: Distributed Map đọc CSV từ S3

Ví dụ giả định có object **s3://batch-lab-input-example/imports/2026-11-20/orders.csv**:

~~~csv
orderId,totalAmount,currency
o-101,120.00,USD
o-102,85.50,USD
o-103,32.00,USD
~~~

Workflow mẹ đọc CSV với header ở dòng đầu, gửi từng bản ghi cho một Lambda processor, giới hạn concurrency **50** và ghi kết quả ra bucket S3 cùng account/Region.

~~~json
{
  "Comment": "Example Distributed Map processing a CSV dataset",
  "StartAt": "ProcessCsv",
  "States": {
    "ProcessCsv": {
      "Type": "Map",
      "ItemReader": {
        "Resource": "arn:aws:states:::s3:getObject",
        "ReaderConfig": {
          "InputType": "CSV",
          "CSVHeaderLocation": "FIRST_ROW"
        },
        "Parameters": {
          "Bucket": "batch-lab-input-example",
          "Key": "imports/2026-11-20/orders.csv"
        }
      },
      "ItemSelector": {
        "record.$": "$$.Map.Item.Value",
        "index.$": "$$.Map.Item.Index"
      },
      "ItemProcessor": {
        "ProcessorConfig": {
          "Mode": "DISTRIBUTED",
          "ExecutionType": "STANDARD"
        },
        "StartAt": "ProcessOne",
        "States": {
          "ProcessOne": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:process-one",
              "Payload.$": "$"
            },
            "OutputPath": "$.Payload",
            "Retry": [
              {
                "ErrorEquals": [
                  "Lambda.ServiceException",
                  "Lambda.AWSLambdaException",
                  "Lambda.SdkClientException"
                ],
                "IntervalSeconds": 2,
                "BackoffRate": 2,
                "MaxAttempts": 3
              }
            ],
            "End": true
          }
        }
      },
      "MaxConcurrency": 50,
      "ToleratedFailureCount": 5,
      "ResultWriter": {
        "Resource": "arn:aws:states:::s3:putObject",
        "Parameters": {
          "Bucket": "batch-lab-results-example",
          "Prefix": "results/2026-11-20/"
        }
      },
      "End": true
    }
  }
}
~~~

**Đây là ASL mẫu với tên tài nguyên giả định.** Nó không thể chạy thành công cho đến khi bucket/input CSV, Lambda function, IAM execution role và KMS permissions tương ứng được tạo. Ví dụ dùng **QueryLanguage JSONPath** mặc định; với workflow **JSONata**, một số trường có cách viết khác như **Arguments** thay **Parameters**, **Items** thay **ItemsPath**. Không trộn hai kiểu cú pháp.

### 7.1. Diễn giải các trường quan trọng

| Trường | Vai trò | Trong ví dụ |
|---|---|---|
| **ItemReader** | Đọc records đầu vào | CSV S3, header FIRST_ROW |
| **ItemSelector** | Đóng gói mỗi record và index | Child input gồm **record**, **index** |
| **ItemProcessor** | Steps xử lý mỗi record | Lambda Invoke |
| **Mode: DISTRIBUTED** | Tạo child executions trong Map Run | Distributed processing |
| **ExecutionType: STANDARD** | Chọn child Standard | Có execution history riêng |
| **MaxConcurrency: 50** | Tối đa 50 child đang xử lý đồng thời | Tránh bắn 10.000 Lambda lên RDS |
| **ToleratedFailureCount: 5** | Cho phép tối đa 5 items/child thất bại trước khi Map Run vượt ngưỡng | Không bỏ qua kết quả lỗi; xem ResultWriter |
| **ResultWriter** | Xuất kết quả theo trạng thái ra S3 | Kết quả không tích tụ thành payload khổng lồ |

**ToleratedFailureCount = 5 không có nghĩa Map chắc chắn kết thúc ngay đúng lúc child thứ sáu lỗi.** AWS có thể đã dispatch các child khác và một số có thể tiếp tục xử lý khi ngưỡng vừa bị vượt. Backend phải chịu được overlap và duplicate execution khi retry/redrive.

### 7.2. Đầu vào thực tế của child

Một child có thể nhận:

~~~json
{
  "record": {
    "orderId": "o-101",
    "totalAmount": "120.00",
    "currency": "USD"
  },
  "index": 0
}
~~~

CSV reader thường tạo **giá trị chuỗi**; ứng dụng Java cần parse amount đúng loại với **BigDecimal**, xác minh currency và schema. Đừng giả định dữ liệu CSV đã là JSON number hoặc tin mọi dòng hợp lệ. Dùng **record ID + dataset version/job ID** làm idempotency key và tránh tác động tài chính hai lần.

### 7.3. Kết quả được ghi ở đâu?

**ResultWriter** xuất dữ liệu child runs vào S3 theo trạng thái và định dạng cấu hình, thay vì đưa tất cả records quay lại parent dưới giới hạn 256 KiB. Cần theo dõi output path, IAM **s3:PutObject** và KMS permissions nếu bucket dùng SSE-KMS. **Bucket ResultWriter phải cùng AWS account và Region với state machine** theo tài liệu AWS; khác điều kiện có thể báo **States.ResultWriterFailed**.

## 8. ItemReader: các nguồn dữ liệu, format và an toàn

Trong Distributed Map, **ItemReader** mô tả tập items cho Map Run. Tùy nhu cầu, nó có thể nhận:

| Nguồn | Cách đọc | Điều chú ý |
|---|---|---|
| JSON array/object từ state input | Không nhất thiết có ItemReader S3 | Vẫn chịu 256 KiB payload parent |
| **CSV S3** | **s3:getObject** + InputType CSV | Header, delimiter, encoding, schema, PII |
| **JSON S3** | InputType JSON | Có thể chọn node cụ thể bằng **ItemsPointer** |
| **JSON Lines S3** | InputType JSONL | Mỗi record/line hợp lệ |
| **Parquet S3** | InputType PARQUET | Dữ liệu cột, type/schema, quyền S3 |
| **S3 object listing** | **s3:listObjectsV2** | Trả object metadata hoặc đọc nội dung với Transformation |
| **Athena manifest** | Manifest cho các data files | Đảm bảo tập input nhất quán và quyền source |
| **S3 Inventory manifest** | Danh sách objects theo inventory | Schema và files theo định dạng inventory được hỗ trợ |

Tính năng ItemReader hiện có thể sử dụng các compression formats như **GZIP/ZSTD** theo loại dữ liệu được AWS hỗ trợ. AWS cũng hỗ trợ **Transformation: LOAD_AND_FLATTEN** với nguồn **S3 ListObjectsV2** để đọc và xử lý bản ghi trong các objects, thay vì chỉ lặp metadata object.

**Không chọn prefix thiếu dấu slash khi listing S3.** Prefix **exports/order** có thể match cả **exports/orders/** và **exports/order-backup/** tùy tên; thêm dấu **/** và xác minh phạm vi objects. Kết hợp least-privilege **s3:ListBucket** theo prefix và **s3:GetObject** đúng tài nguyên.

### 8.1. Kích thước nguồn khác kích thước mỗi child input

Một input CSV S3 có thể lớn hơn 256 KiB, nhưng **input/output của mỗi child execution vẫn bị giới hạn 256 KiB**. AWS công bố các giới hạn riêng cho **mỗi file nguồn S3** và các định dạng được hỗ trợ; với item quá lớn, cần **ItemSelector** để chỉ lấy trường cần thiết hoặc lưu payload lớn ở S3 rồi truyền object key. Không đưa toàn bộ file nhị phân/base64 vào một child input.

Nếu dùng **ItemsPointer** cho JSON nested, phải xác minh node trỏ đúng array/object. Nếu dùng **LOAD_AND_FLATTEN**, nó thay semantics từ **một child trên mỗi object metadata** sang **items từ nội dung files**; cần kiểm thử fan-out count để tránh khởi động số lượng children vượt dự toán.

## 9. ItemBatcher: gộp items để giảm orchestration overhead

**ItemBatcher** trong Distributed Map gom nhiều items vào **một child execution**. Hữu ích khi có 1.000.000 rows nhưng mỗi row chỉ cần xử lý vài milliseconds, trong khi tạo một execution cho mỗi row gây overhead/chi phí lớn.

Ví dụ khai báo:

~~~json
{
  "ItemBatcher": {
    "MaxItemsPerBatch": 100,
    "MaxInputBytesPerBatch": 131072,
    "BatchInput": {
      "schemaVersion": "2026-11"
    }
  }
}
~~~

Đây là **fragment** gắn bên trong Distributed Map, không phải một state machine hoàn chỉnh. **MaxItemsPerBatch = 100** và **MaxInputBytesPerBatch = 131.072 bytes** (128 KiB) khiến mỗi child nhận tối đa 100 items và không vượt ngưỡng size đã đặt. Nếu hai giới hạn cùng khai báo, giới hạn nào đến trước sẽ quyết định batch cuối cùng. Kích thước batch input vẫn phải nằm trong quota Step Functions.

Child input thường có cấu trúc:

~~~json
{
  "BatchInput": {
    "schemaVersion": "2026-11"
  },
  "Items": [
    {"orderId": "o-101"},
    {"orderId": "o-102"}
  ]
}
~~~

**Trade-off:** batching giảm số child workflows nhưng tăng thời gian mỗi child và phạm vi retry. Nếu một row lỗi làm **cả batch** thất bại, có thể phải chạy lại hàng trăm rows đã xử lý thành công. Worker nên trả **per-item outcomes**, dùng checkpoint/idempotency và thiết kế cách cô lập poison records trước khi quyết định batch size.

### 9.1. Ảnh hưởng tới concurrency

Nếu Map có **MaxConcurrency = 50** và mỗi batch chứa 100 rows, tối đa khoảng **5.000 rows có thể đang được xử lý trong 50 child executions**, nhưng đây chỉ là mức suy luận theo batch size; không có bảo đảm thực tế workers xử lý 100 rows song song. Một child Lambda có thể xử lý 100 rows **tuần tự**, và tổng throughput phụ thuộc handler duration, memory, database và service quotas.

## 10. Data transformation: InputPath, ItemSelector, ResultSelector, ResultPath

Một state Step Functions chỉ nên truyền **dữ liệu cần thiết**, không phải toàn bộ response từ mọi dịch vụ. Với ví dụ Lambda Invoke, kết quả có thể chứa metadata SDK/HTTP, trong khi branch tiếp theo chỉ cần **Payload**.

| Thành phần | Vị trí thường dùng | Công dụng |
|---|---|---|
| **InputPath** | JSONPath state | Lọc một phần input state |
| **Parameters** | JSONPath Task/Pass và các integrations | Tạo request payload cho Task |
| **ItemsPath** | JSONPath Map | Chọn array để lặp |
| **ItemSelector** | Map | Tạo input của mỗi iteration/child từ value/index/global state |
| **ResultSelector** | JSONPath state | Chọn/đổi cấu trúc kết quả trước ResultPath |
| **ResultPath** | JSONPath state | Gộp kết quả vào input, hoặc bỏ result với **null** |
| **OutputPath** | JSONPath state | Lọc output cuối của state |
| **ResultWriter** | Distributed Map | Xuất child results ra S3 thay vì giữ tập output lớn |
| **Assign / Output** | JSONata hoặc workflow variables theo hỗ trợ | Cách biểu diễn/biến đổi khác, không dùng lẫn các trường JSONPath một cách máy móc |

### 10.1. Ba cách tránh States.DataLimitExceeded

1. **Giữ references thay vì datasets:** truyền **s3://bucket/key**, một record ID hoặc job ID, không mang toàn bộ file trong state.
2. **Giảm output per item:** dùng **OutputPath/ResultSelector** để loại metadata không cần, hoặc **ResultPath: null** nếu side effect đã được lưu ở database.
3. **Sử dụng ResultWriter** cho Distributed Map để ghi kết quả lớn ra S3 và chỉ truyền đường dẫn/summary cho các states sau.

**States.DataLimitExceeded** không phải lỗi có thể “retry đến khi hết”. Khi state input/output đã vượt hard quota 256 KiB, phải thay thiết kế dữ liệu; generic Catch **States.ALL** không xử lý được mọi loại lỗi terminal này theo cách mong muốn.

## 11. Retry, Catch và ngưỡng lỗi khi xử lý song song

**Retry** là thử lại một Task/State khi gặp lỗi đã định nghĩa; **Catch** là chuyển sang nhánh xử lý lỗi sau khi retry cạn hoặc khi lỗi không thuộc danh sách retry. Đây là những tính năng điều phối, **không tự rollback** dữ liệu đã được ghi vào S3, DynamoDB, RDS hoặc hệ thống ngoài.

### 11.1. Retry có giới hạn và exponential backoff

Ví dụ fragment Task gọi Lambda, retry một số lỗi tạm thời:

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Parameters": {
    "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:validate-one",
    "Payload.$": "$"
  },
  "OutputPath": "$.Payload",
  "Retry": [
    {
      "ErrorEquals": [
        "Lambda.ServiceException",
        "Lambda.AWSLambdaException",
        "Lambda.SdkClientException"
      ],
      "IntervalSeconds": 2,
      "MaxAttempts": 3,
      "BackoffRate": 2
    }
  ],
  "End": true
}
~~~

Đây là **Task state fragment**, không phải state machine hoàn chỉnh. Với nhiều tasks xử lý đồng thời, nên dùng **MaxDelaySeconds/JitterStrategy** hoặc chiến lược có jitter theo khả năng Step Functions, để tránh retry storm. Không retry vô hạn **validation errors, invalid input, permission denied** hoặc các thao tác tài chính chưa idempotent.

### 11.2. Catch ở từng branch hoặc từng item

Nếu muốn batch **có bản ghi lỗi nhưng không hủy toàn bộ công việc**, có thể Catch ngay bên trong **ItemProcessor**:

~~~json
{
  "ProcessOne": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke",
    "Parameters": {
      "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:validate-one",
      "Payload.$": "$"
    },
    "OutputPath": "$.Payload",
    "Catch": [
      {
        "ErrorEquals": ["States.ALL"],
        "ResultPath": "$.error",
        "Next": "RecordFailure"
      }
    ],
    "End": true
  },
  "RecordFailure": {
    "Type": "Pass",
    "Parameters": {
      "ok": false,
      "reason.$": "$.error.Error"
    },
    "End": true
  }
}
~~~

Hai state definitions ở trên là **fragment cho States của ItemProcessor**, không phải ASL độc lập. Khi **Catch chuyển lỗi thành một output thành công**, Step Functions xem **child execution thành công ở mức workflow**: **ToleratedFailureCount/Percentage sẽ không tính record đó là child thất bại**. Nếu muốn Map Run thực sự ghi nhận lỗi theo failure threshold, để child thất bại sau khi xử lý thông tin cần lưu, hoặc dùng **Fail state** có kiểm soát.

Với Parallel, một branch có thể tự Catch và trả object **ok=false** để parent đánh giá tình trạng tất cả branches. Nhưng nếu một nhánh thực thi thao tác không thể đảo ngược, lỗi ở nhánh khác vẫn cần **compensation/saga** riêng; không coi Catch như database transaction rollback.

### 11.3. Ngưỡng lỗi Distributed Map

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| **ToleratedFailureCount** | Số items thất bại được phép | 5 |
| **ToleratedFailurePercentage** | Tỷ lệ failed/timed-out items chấp nhận | 2% |
| **ToleratedFailureCountPath** | Giá trị count lấy động từ input (JSONPath) | $.allowFailures |
| **ToleratedFailurePercentagePath** | Tỷ lệ lấy động từ input (JSONPath) | $.allowFailurePct |
| **States.ExceedToleratedFailureThreshold** | Lỗi Map Run khi vượt ngưỡng | Cần xem item failures và kết quả export |

Nếu không đặt tolerance, mặc định **0% lỗi được chấp nhận**. Nếu đặt cả count và percentage, **vượt một trong hai** sẽ khiến Map Run thất bại. Tolerance giúp diễn tả business requirement như “cho phép tối đa 10 dòng sai”, nhưng **không biến dữ liệu lỗi thành dữ liệu đúng**. Workflow sau Map cần xem thống kê và báo cáo record lỗi.

### 11.4. Phân biệt lỗi hạ tầng và lỗi nghiệp vụ

| Loại | Ví dụ | Hành động hợp lý |
|---|---|---|
| **Transient** | Lambda 5xx, throttling, network timeout | Retry có backoff + jitter |
| **Permanent input** | CSV sai schema, object key không tồn tại | Ghi failure record/DLQ, không retry vô hạn |
| **Authorization** | AccessDenied S3, IAM role không có quyền | Sửa role, KMS, resource policy |
| **Capacity** | RDS max connections, downstream rate limit | Hạ concurrency, queue/throttle, tăng capacity có căn cứ |
| **Data limit** | State output lớn hơn 256 KiB | Truyền S3 reference/ResultWriter |
| **Tolerated failure exceeded** | Quá nhiều child workflows lỗi | Điều tra dataset, sửa worker rồi redrive |

### 11.5. Lưu ý States.ALL và các lỗi terminal

**States.ALL** là wildcard nhiều lỗi trong Retry/Catch, nhưng **không bắt được mọi lỗi Step Functions**. Những lỗi như **States.Runtime** và **States.DataLimitExceeded** có tính terminal theo quy tắc dịch vụ; không dùng một Catch chung để che mọi lỗi JSONPath/data transformation. Cần kiểm tra ASL đầu vào, paths và payload size trước deployment.

## 12. Redrive, idempotency và khôi phục công việc batch

**Redrive** là khả năng chạy lại execution thất bại theo điều kiện AWS hỗ trợ. Với **Distributed Map**, khi parent **Standard execution** đủ điều kiện redrive, Step Functions có thể redrive những child executions không thành công trong Map Run thay vì bắt buộc làm lại mọi item. Có sự khác nhau:

- **Standard child:** được redrive theo trạng thái lỗi từ execution gốc khi đủ điều kiện, giúp giữ lịch sử chi tiết.
- **Express child:** khi redrive Map Run, child lỗi được **khởi chạy lại từ đầu** theo cơ chế StartExecution, không phải resume từng state.
- **Parent Standard execution** có các điều kiện về trạng thái, thời hạn redrive và history quota. AWS hiện mô tả **14 ngày** là cửa sổ redrive kể từ khi execution kết thúc, cùng các ràng buộc khác.
- Một số lỗi **States.DataLimitExceeded/States.Runtime** có thể dẫn tới Map Run mới hoặc không đủ điều kiện redrive theo semantics; phải đối chiếu trạng thái thực tế.

**Redrive không tự động xóa những tác dụng phụ đã xảy ra trước khi thất bại.** Ví dụ child ghi order vào DB rồi timeout trước khi đánh dấu success sẽ được retry/redrive và có thể ghi trùng nếu code không idempotent.

### 12.1. Idempotency key

Nên dùng một khóa ổn định như:

~~~text
jobId + datasetVersion + recordId + operationType
~~~

Ví dụ **import-2026-11-20 + s3-etag-or-version + o-101 + upsert**. Đừng chỉ dùng Map Item.Index nếu dataset có thể thay đổi thứ tự hoặc tạo file mới. Có thể đặt **unique constraint**, condition write trong DynamoDB hoặc transaction semantics phù hợp để cùng một event chạy lại nhưng không gây side effect trùng.

### 12.2. Có thật sự cần tự bù trừ?

| Thao tác | Mức rủi ro replay | Biện pháp |
|---|---|---|
| Đọc ảnh từ S3, tạo thumbnail với tên deterministic | Thấp hơn | Upsert/overwrite có điều kiện, kiểm tra version |
| Nạp catalog bằng upsert | Trung bình | Kiểm tra schema, idempotency key, version |
| Gửi email/SMS | Cao về duplicate notification | Notification dedupe và trạng thái gửi |
| Thu tiền / refund | Rất cao | Payment idempotency key, ledger, saga/compensation |
| Ghi nhiều hệ thống độc lập | Cao | Transactional outbox, saga, audit trạng thái |

Với Parallel chứa nhiều nhánh ghi dữ liệu, tránh **Retry của toàn Parallel** nếu không có hợp đồng idempotency. Với Distributed Map, đặt **failure tolerance** theo nghiệp vụ và báo cáo danh sách records cần xử lý thủ công.

## 13. Concurrency và backpressure: nhanh nhưng không làm sập backend

Đặt concurrency không chỉ dựa vào số CPU của Step Functions. Giới hạn quan trọng nằm ở **Lambda Reserved/Account Concurrency, ECS/Batch quota, RDS connections, DynamoDB RCUs/WCUs, API rate limits, NAT/VPCE và service throttling**.

### 13.1. Ước lượng đơn giản

Nếu một worker xử lý trung bình **2 giây/item**, MaxConcurrency **50** có throughput lý tưởng xấp xỉ **25 item/giây** khi không có overhead hay throttling. Nhưng một database chỉ chịu **10 writes/giây** sẽ trở thành bottleneck; tăng MaxConcurrency lên 500 chỉ tạo thêm retries và chi phí.

**Đây chỉ là ví dụ xấp xỉ.** Trong thực tế latency phân phối, batch size, cold starts, retry, network, Lambda throttles và capacity thay đổi theo thời gian. Đo throughput/p95/p99 và backlog thật rồi điều chỉnh.

### 13.2. Giới hạn động

Với workflow JSONPath, bạn có thể đặt:

~~~json
{
  "MaxConcurrencyPath": "$.workerLimit"
}
~~~

Đây là **fragment Map state**. Input cần có **workerLimit** là số nguyên hợp lệ; **không** khai báo đồng thời **MaxConcurrency** và **MaxConcurrencyPath**. Với JSONata có thể dùng expression theo cách ASL hỗ trợ. Nếu người dùng được tự nhập concurrency không kiểm tra, họ có thể khiến workflow đột ngột gọi hàng nghìn services và vượt chi phí; nên ràng buộc giá trị theo policy/capacity của tổ chức.

### 13.3. Cách bảo vệ downstream

1. Đặt **MaxConcurrency nhỏ** khi mới chạy batch production; tăng qua load test.
2. Giới hạn Lambda concurrency và container worker capacity riêng.
3. Dùng **retries với backoff/jitter** khi nhận 429/5xx; giới hạn retry count và tổng thời gian.
4. Sử dụng **ItemBatcher** nếu mỗi row quá nhỏ, nhưng chỉ tăng batch khi handler chịu tải.
5. Dùng **SQS** để đệm công việc cần chịu tải dài hạn, hoặc **AWS Batch/ECS** cho CPU-heavy workloads.
6. Với database, dùng connection pooling/proxy/partitioning khi đúng nhu cầu; kiểm tra consistency.
7. Có timeout, cancellation/compensation và cảnh báo vượt ngưỡng.

### 13.4. Những quota phải xác minh trước khi go-live

| Quota/giới hạn | Giá trị tham khảo từ tài liệu AWS | Ý nghĩa |
|---|---|---|
| State input/output | **256 KiB** | Giới hạn data payload của state/execution |
| Standard history | **25.000 events** | Inline iterations đóng góp vào parent history |
| Inline Map | **40 concurrent iterations** | Dữ liệu trong JSON array |
| Distributed Map | **10.000 concurrent child executions** mỗi Map Run | Hard upper bound, không phải mức khuyến nghị |
| Open Map Runs | **1.000** mỗi account/Region theo tài liệu quota | Map Run mới có thể pending khi vượt quota |
| Express execution duration | **Tối đa 5 phút** | Không hợp job item kéo dài nhiều giờ |
| Standard execution duration | **Tối đa 1 năm** | Phù hợp workflow dài theo quota |
| Định nghĩa state machine | **1 MiB** theo quota API | Không inline hàng nghìn items trong definition |

Giới hạn/throttling AWS có thể phụ thuộc Region và thay đổi theo thời gian. Ngoài hard quota, cần quan sát throughput điều phối, **StartExecution API**, Lambda API, S3 request, Batch và downstream services. Tra **Service Quotas** cho account/Region thực tế trước vận hành.

## 14. IAM và bảo mật khi chạy Parallel/Map

**Step Functions execution role** được dịch vụ Step Functions assume để gọi Task integrations, đọc dataset và ghi kết quả. Các **Lambda execution roles**, **ECS task roles** hoặc **AWS Batch job roles** vẫn quản lý quyền nghiệp vụ của từng worker.

### 14.1. Ma trận quyền

| Principal | Quyền minh họa | Vì sao |
|---|---|---|
| **State machine role** | **lambda:InvokeFunction** cho worker | Step Functions gọi Lambda |
| **State machine role** | **s3:GetObject** cho input prefix | Distributed Map ItemReader đọc dataset |
| **State machine role** | **s3:PutObject** cho result prefix | ResultWriter xuất child results |
| **State machine role** | **states:StartExecution/DescribeExecution** trên chính child workflow theo ARN tương ứng | Distributed Map tạo và giám sát child executions |
| **Worker Lambda role** | Quyền đọc/ghi DynamoDB, S3, RDS secrets theo business | Handler làm nghiệp vụ |
| **Operator IAM principal** | DescribeExecution/DescribeMapRun/ListMapRuns, xem log | Theo dõi batch mà không sửa production |
| **CI/CD role** | Create/UpdateStateMachine, IAM PassRole với giới hạn | Quản trị workflow có kiểm soát |

Ví dụ **identity-based IAM policy fragment** cho state machine role dùng ASL ở phần 7:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadBatchInput",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::batch-lab-input-example/imports/*"
    },
    {
      "Sid": "WriteBatchResults",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::batch-lab-results-example/results/*"
    },
    {
      "Sid": "InvokeOnlyWorker",
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:ap-southeast-1:111122223333:function:process-one"
    },
    {
      "Sid": "StartChildWorkflow",
      "Effect": "Allow",
      "Action": "states:StartExecution",
      "Resource": "arn:aws:states:ap-southeast-1:111122223333:stateMachine:batch-workflow"
    },
    {
      "Sid": "ObserveChildWorkflow",
      "Effect": "Allow",
      "Action": "states:DescribeExecution",
      "Resource": "arn:aws:states:ap-southeast-1:111122223333:execution:batch-workflow:*"
    }
  ]
}
~~~

**Đây là mẫu cần thay ARN và hiệu chỉnh theo integration thực tế**, không phải gói permissions đầy đủ cho mọi workflow. Redrive có thể cần **states:RedriveExecution** trên execution ARNs theo hướng dẫn. Nếu nguồn S3 dùng **SSE-KMS**, bucket policy/KMS key policy và quyền **kms:Decrypt** phải cho đúng state machine role; ResultWriter S3 SSE-KMS có thể cần quyền **kms:GenerateDataKey** và key policy phù hợp. **IAM Allow không thắng explicit Deny** ở bucket, KMS, SCP hay VPC endpoint policy.

### 14.2. Least privilege trên dataset

Không cấp **s3:* trên toàn account** cho state machine chỉ vì phải đọc 1 CSV. Đặt bucket/prefix thật, yêu cầu HTTPS, sử dụng KMS/bucket policies và S3 versioning khi cần reproducibility. Nếu reader dùng **ListObjectsV2**, cần **s3:ListBucket** trên bucket với condition prefix phù hợp, khác với **s3:GetObject** trên object ARN.

### 14.3. Bảo vệ dữ liệu nhạy cảm

- **Không đưa PII hoặc secrets nguyên văn vào execution name, state input/output hoặc CloudWatch Logs** nếu không cần.
- Với workflow được dùng bởi nhiều tenants, tách dataset prefixes, KMS permissions, job metadata và kết quả theo tenant.
- Kiểm tra quyền **StartExecution/StopExecution/RedriveExecution**; quyền chạy lại workflow có thể gây business side effects.
- Với callback pattern, task token là dữ liệu nhạy cảm; không log hoặc chia sẻ không kiểm soát.
- Dùng **CloudTrail** cho kiểm toán API control plane và logging Step Functions theo cấu hình; không giả định CloudTrail mặc định chứa toàn bộ data payload của từng child.
- Gắn tags/ownership và đặt retention/lifecycle cho **ResultWriter outputs**; batch results có thể chứa input hoặc lỗi nhạy cảm.

## 15. Giám sát và AWS CLI điều tra một Map Run

### 15.1. Các nguồn quan sát

| Nguồn | Quan sát điều gì? |
|---|---|
| **Step Functions execution graph** | State/branch/Map bị lỗi ở đâu |
| **DescribeExecution / GetExecutionHistory** | Parent/Standard child status và transitions |
| **DescribeMapRun** | Tiến độ Map Run, số child succeeded/failed/timed-out/pending |
| **CloudWatch Step Functions metrics** | ExecutionsSucceeded/Failed/TimedOut, Map Run và child metrics tương ứng |
| **CloudWatch Logs** | Workflow logs theo cấu hình, đặc biệt Express |
| **Lambda/ECS/Batch logs** | Lỗi ứng dụng, timeout, network và retries |
| **S3 ResultWriter outputs** | Các thành công/thất bại và dữ liệu từng child |
| **CloudTrail** | Ai cập nhật definition/role hoặc gọi StartExecution/Redrive |

**Map Run thành công không đảm bảo 100% records thành công** nếu bạn đã cấu hình failure tolerance hoặc bắt lỗi bên trong child thành trạng thái success. Hãy đọc **Map Run item counts, ResultWriter error files và business reconciliation** trước khi đánh dấu job hoàn tất.

### 15.2. Validate ASL trước deployment

Nếu đã lưu mẫu ASL vào một file trong dự án của bạn (không phải bước thực hiện trong bài này):

~~~bash
# Chỉ kiểm tra definition, không tạo state machine.
aws stepfunctions validate-state-machine-definition \
  --region ap-southeast-1 \
  --definition file://workflow.asl.json \
  --type STANDARD
~~~

API trả **result = OK/FAIL** cùng diagnostics. Automation nên dựa vào **result**, không hard-code thông điệp cảnh báo vì AWS có thể điều chỉnh diagnostics. Validation tĩnh **không chứng minh** Lambda ARNs, IAM, S3 keys, network và KMS đều hoạt động; phải kiểm thử staging.

### 15.3. Kiểm tra execution và Map Run (read-only)

~~~bash
# Xem execution parent.
aws stepfunctions describe-execution \
  --region ap-southeast-1 \
  --execution-arn arn:aws:states:ap-southeast-1:111122223333:execution:batch-workflow:run-001

# Liệt kê Map Runs của execution parent.
aws stepfunctions list-map-runs \
  --region ap-southeast-1 \
  --execution-arn arn:aws:states:ap-southeast-1:111122223333:execution:batch-workflow:run-001

# Dùng MapRunArn thật trả về từ list-map-runs.
aws stepfunctions describe-map-run \
  --region ap-southeast-1 \
  --map-run-arn arn:aws:states:ap-southeast-1:111122223333:mapRun:batch-workflow/demo:REPLACE_UUID

# Có thể xem các child executions của một Map Run.
aws stepfunctions list-executions \
  --region ap-southeast-1 \
  --map-run-arn arn:aws:states:ap-southeast-1:111122223333:mapRun:batch-workflow/demo:REPLACE_UUID
~~~

**REPLACE_UUID** chỉ là placeholder; ARN Map Run có định dạng do AWS trả về, không tự đoán từ execution ID. Với **Express child**, truy cập lịch sử/traces khác Standard; bật logging thích hợp và sử dụng khả năng theo dõi Map Run. Nếu Lambda lỗi vì database, DescribeMapRun chỉ cho biết child failed, còn nguyên nhân cần đọc Lambda logs/metrics.

### 15.4. Redrive có tác động lên dữ liệu

~~~bash
# Lệnh thay đổi trạng thái: chỉ chạy khi đã sửa lỗi gốc,
# kiểm tra idempotency, ngân sách và có phê duyệt.
aws stepfunctions redrive-execution \
  --region ap-southeast-1 \
  --execution-arn arn:aws:states:ap-southeast-1:111122223333:execution:batch-workflow:run-001
~~~

Redrive có thể **khởi chạy lại những child executions không thành công**, gây ghi lại database hoặc gửi thông báo lần nữa nếu handler không idempotent. Trước khi chạy, xem trạng thái eligibility, replay semantics của Standard/Express children, KMS permissions và tình hình dataset.

## 16. Kiến trúc ví dụ: nhập catalog dữ liệu hàng loạt

**Bối cảnh:** hàng ngày một đối tác xuất file **products.csv** vào S3, chứa khoảng 300.000 dòng. Hệ thống cần kiểm tra dữ liệu, chuẩn hóa từng sản phẩm, ghi vào DynamoDB và tạo báo cáo lỗi; sau khi hoàn tất mới gửi thông báo.

### 16.1. Thiết kế tổng thể

~~~mermaid
flowchart TD
    S3["S3 input dataset<br/>products.csv"] --> EVT["EventBridge / Scheduler"]
    EVT --> PARENT["Step Functions Standard parent"]
    PARENT --> PRE["Validate manifest/schema<br/>Lambda Task"]
    PRE --> MAP["Distributed Map<br/>MaxConcurrency=100"]
    S3 --> READER["ItemReader CSV"]
    READER --> BATCH["ItemBatcher<br/>ví dụ 50 rows/child"]
    BATCH --> MAP
    MAP --> CHILD["Child workflow<br/>Validate → Normalize → Upsert"]
    CHILD --> DDB["DynamoDB<br/>Idempotent writes"]
    MAP --> RESULT["ResultWriter S3<br/>success/failure"]
    RESULT --> SUMMARY["Summarize counts/errors"]
    SUMMARY --> NOTIFY["SNS / EventBridge notification"]
    SUMMARY --> AUDIT["DynamoDB job ledger<br/>jobId + status"]
~~~

### 16.2. Thứ tự thiết kế

1. **Nguồn dữ liệu bất biến:** lưu input S3 với **VersionId/ETag**, biết chính xác dataset đã xử lý.
2. **Khởi tạo job:** tạo **jobId**, ghi job metadata, khóa idempotency theo job/version để tránh trigger lặp.
3. **Validate sơ bộ:** xác minh kích thước, schema/header, encoding và IAM/KMS trước khi fan-out.
4. **Distributed Map:** đọc CSV từ S3, chọn các fields cần, batch có kiểm soát.
5. **Worker:** parse loại dữ liệu đúng, kiểm tra business rules, upsert có điều kiện theo sản phẩm/phiên bản.
6. **ResultWriter:** ghi child results, phân biệt succeeded/failed records và giữ path báo cáo.
7. **Reconcile:** tổng record input = thành công + thất bại + trạng thái chưa rõ; lưu thống kê và kiểm tra tolerance.
8. **Notify:** chỉ gửi trạng thái đã kiểm chứng; nếu có partial failures phải thông báo rõ, không ghi “100% thành công”.
9. **Retention:** S3 lifecycle policy cho input/results, CloudWatch logs và job ledger.

### 16.3. Khi nào dùng Parallel trong cùng kiến trúc?

Trước Distributed Map, hệ thống có thể chạy **Parallel** để:

- Xác minh **schema CSV**.
- Kiểm tra **danh mục tham chiếu/currency codes**.
- Kiểm tra **storage quota và quyền bucket**.

Ba nhánh này là **những phép kiểm tra khác logic** cùng đọc job metadata. Sau khi tất cả thành công, parent chuyển sang Distributed Map. **Không** dùng Parallel để khai báo thủ công 300.000 branches; Map mới là mô hình lặp theo dataset.

### 16.4. Thất bại 2% records thì sao?

Nếu nghiệp vụ chấp nhận tối đa 2% invalid rows, có hai cách khác nhau:

| Cách | Hệ quả |
|---|---|
| Worker trả **error object nhưng child success** | Map Run **không** tính child failed; phải tự tổng hợp tỷ lệ invalid rows |
| Worker child **Fail** cho invalid item và Map có ToleratedFailurePercentage | Map Run đếm failed items/children; cần đảm bảo không đánh đồng retryable với permanent lỗi |

Với **ItemBatcher**, một child chứa 50 records có thể bị xem là một execution lỗi dù thực tế chỉ một record sai; tỷ lệ lỗi của Map Run lúc đó không tự bằng tỷ lệ dòng CSV sai. Nếu business requirement dựa trên tỷ lệ **records**, hãy thiết kế worker xuất **per-record outcomes** rồi reconcile theo **record count**, không coi số failed child batches là số failed rows.

### 16.5. Sự cố một AZ và khả năng phục hồi

Step Functions là dịch vụ theo Region do AWS quản lý; worker Lambda/ECS có cơ chế availability và giới hạn riêng. Nếu task ECS chạy tại một AZ có sự cố, child cần retry/backoff và khả năng schedule sang AZ khỏe, trong khi dữ liệu S3 và DynamoDB có kiến trúc khu vực được quản lý theo SLA tương ứng. Multi-AZ của backend **không tự giải quyết** retry gây ghi trùng, thiếu permissions hoặc mô hình dữ liệu lỗi.

**Step Functions Distributed Map không phải một giải pháp DR Multi-Region mặc định.** Nếu yêu cầu RTO/RPO cấp Region, phải lập kế hoạch riêng cho state machine definition, input/output S3, KMS, worker image, database replication, event replay và quyết định không phát lại hai lần.

## 17. Runbook xử lý sự cố Parallel/Map

### 17.1. Bảng triệu chứng và điều tra

| Triệu chứng | Nguyên nhân có thể | Bằng chứng ưu tiên |
|---|---|---|
| **Parallel failed sớm** | Một branch không Catch lỗi, hoặc Fail state | Execution history từng branch, Task logs |
| **Cả workflow báo thành công nhưng thiếu một check** | Branch Catch thành result ok=false rồi parent không kiểm tra | Output array và validation fan-in |
| **Inline Map lỗi States.DataLimitExceeded** | Output array lớn/đưa nguyên Lambda metadata vào state | Execution input/output size, OutputPath/ResultPath |
| **Inline Map lỗi history limit** | Quá nhiều iterations, retries, Task transitions | Parent execution event count, dự toán 25.000 events |
| **ItemsPath không tìm thấy array** | InputPath đã lọc mất trường hoặc key sai | Test input path, dữ liệu state trước Map |
| **Child nhận input thiếu record** | ItemSelector tham chiếu sai Context/Data path | Xem JSON đầu vào ChildExecution |
| **Distributed Map không đọc được S3** | Thiếu s3:GetObject/ListBucket, KMS Decrypt, object key sai | ItemReader path, state machine IAM role, KMS |
| **States.ItemReaderFailed** | Dataset không đọc được/định dạng không hợp lệ | ItemReader, S3 source, permissions/schema |
| **States.ResultWriterFailed** | S3 result bucket sai account/Region, thiếu PutObject/KMS | ResultWriter path, bucket/role policy, KMS |
| **States.ExceedToleratedFailureThreshold** | Quá nhiều child failed/timed out | DescribeMapRun counts, child errors, worker logs |
| **Child Lambda bị throttling** | MaxConcurrency quá lớn, reserved/account concurrency thấp | Lambda Throttles/ConcurrentExecutions |
| **DB connection storm** | Child workflows cùng mở kết nối/ghi | RDS connections/latency, backoff/concurrency |
| **Map Run Pending lâu** | Throttle/dispatch/quota open Map Runs hoặc capacity | DescribeMapRun, Service Quotas, status events |
| **S3 output thiếu hoặc rỗng** | Child outputs không hợp lệ, ResultWriter/path/permissions sai | ResultWriter artifacts, Map status, worker result |
| **Redrive làm trùng transaction** | Worker không idempotent, child replay side effect | Job ledger, idempotency key, DB/notification log |
| **Chi phí Step Functions tăng** | Quá nhiều child executions/state transitions/retries/logs | Cost Explorer, transition metrics, Map counts |

### 17.2. Trình tự phân tích một Distributed Map thất bại

~~~mermaid
flowchart TD
    ALERT["Map Run FAILED / TIMED_OUT"] --> P["Xác định parent execution ARN<br/>và Map Run ARN"]
    P --> STATUS["DescribeMapRun:<br/>Succeeded/Failed/TimedOut/Pending"]
    STATUS --> KIND{"Lỗi thuộc nhóm nào?"}
    KIND -->|"ItemReader / ResultWriter"| IO["S3 key/Region/account,<br/>IAM, KMS, payload"]
    KIND -->|"Child execution"| CHILD["Child error + Lambda/ECS logs<br/>schema, timeout, retries"]
    KIND -->|"Quota / throttling"| LIMIT["MaxConcurrency, Service Quotas,<br/>Lambda/DB/network"]
    IO --> FIX["Sửa nguyên nhân gốc<br/>trong staging"]
    CHILD --> FIX
    LIMIT --> FIX
    FIX --> RECOVER["Kiểm tra idempotency và redrive eligibility"]
    RECOVER --> CHECK["Reconcile records + output + SLO"]
~~~

Các bước:

1. Lấy **parent execution ARN**, Map Run ARN và version của state machine/dataset.
2. Đọc **Map Run status/counters** để xác định lỗi thuộc input, child, output hay orchestration.
3. Với child errors, lấy một mẫu item thất bại; phân nhóm **schema, IAM, KMS, timeout, throttling, business validation**.
4. Kiểm tra **logs** trong đúng Region, dịch vụ worker, child execution ARN và correlation ID.
5. Với capacity errors, giảm concurrency/batch size trước khi tăng quota mù quáng.
6. Sửa nguyên nhân, chạy lại staging với dataset tái hiện, xác minh business side effects idempotent.
7. Nếu đủ điều kiện, **redrive** dưới kiểm soát; nếu không, lập job mới với danh sách failed records và idempotency ledger.
8. Đối soát **input records, successes, failed, skipped, DLQ và output S3** trước khi thông báo hoàn tất.

### 17.3. Vì sao không nên retry toàn bộ khi một item lỗi?

Một input gồm 100.000 records, chỉ có một row chứa ký tự sai định dạng. Retry toàn bộ job 5 lần không sửa được row đó, nhưng tạo thêm state transitions, Lambda/S3/DynamoDB writes và nguy cơ trùng nghiệp vụ. **Permanent validation errors** nên được ghi thành failure record, còn **transient errors** retry một số lần với backoff. Sau sửa source, replay đúng record/batch thất bại.

## 18. Chi phí và tối ưu hóa điều phối

Step Functions có mô hình phí khác nhau giữa **Standard** và **Express**, đồng thời những integrations như Lambda, ECS, Batch, S3, Glue và CloudWatch có phí riêng. Không tính tổng chi phí chỉ bằng số lượng items.

| Hạng mục | Điều cần đưa vào dự toán |
|---|---|
| **Standard transitions** | Số transitions, Retry/Catch, branches và child workflows |
| **Express requests/duration/memory** | Số executions, thời gian chạy và bộ nhớ theo mô hình giá hiện hành |
| **Distributed Map child executions** | Số child starts, loại STANDARD/EXPRESS, số Task states bên trong |
| **ItemBatcher** | Giảm child starts nhưng có thể tăng batch retry và duration |
| **Lambda/ECS/Batch** | CPU/RAM, duration, provisioned capacity, cold starts, Spot |
| **S3/KMS** | GetObject/PutObject/ListObjects, storage, KMS API calls, encryption |
| **CloudWatch/X-Ray** | Logs, metrics/tracing, retention và queries |
| **External dependencies** | RDS/DynamoDB writes, API rate limits, notifications |
| **Redrive/retries** | Những Task và child executions phải chạy lại |

### 18.1. Ví dụ định tính về batching

Với **1.000.000 items**, nếu mỗi item tạo một child execution, bạn có thể có tới một triệu child workflow starts trong toàn bộ job. Nếu batch **100 items**, số child executions lý tưởng giảm còn khoảng **10.000**, đổi lại mỗi child phải xử lý nhiều records và có chiến lược kết quả per-item. Đây là phép tính để hiểu mô hình, **không phải báo giá**; phải xét giới hạn batch payload 256 KiB, item sizes, chi phí worker và yêu cầu retry.

### 18.2. Các cách tối ưu chi phí hợp lệ

- Không tạo Map child cho mỗi record cực nhỏ nếu worker có thể xử lý batch an toàn.
- Dùng **Express child** cho tác vụ ngắn có thể replay và không cần service integration patterns không hỗ trợ.
- Hạn chế retries không cần thiết; phân biệt lỗi schema với lỗi hạ tầng.
- Giảm payload và log verbosity; không xuất toàn bộ data object nhiều lần.
- Đặt **MaxConcurrency theo throughput backend** để tránh throttling/overload tăng phí.
- Thiết kế S3 lifecycle cho input/results và CloudWatch retention.
- So sánh **Step Functions** với **SQS + workers/Glue/Batch** khi workload rất đơn giản, dài hạn hoặc cần buffering thay vì fan-in tập trung.

**Không tối ưu chi phí bằng cách tắt logging, KMS hoặc kiểm tra quyền bừa bãi.** Quyết định phải cân bằng **bảo mật, độ tin cậy, auditability, latency và TCO**.

## 19. Bài tập tình huống

### Tình huống A — Kiểm tra đơn hàng qua ba API

Đơn hàng cần gọi độc lập **Inventory**, **Shipping** và **Fraud**. Kết quả của cả ba phải có trước khi cho phép thanh toán; mỗi API có thể mất 200–800 ms.

**Câu hỏi:** nên dùng Parallel hay Map?

**Gợi ý:** **Parallel** với ba branches độc lập, ResultPath lưu outputs rồi kiểm tra kết quả. Mỗi branch có timeout/retry hợp lý; đối với errors cần quyết định fail fast hay trả object **ok=false**. Không coi Parallel là transaction rollback.

### Tình huống B — 30 sản phẩm cần xác thực

Input một đơn hàng có mảng 30 sản phẩm, mỗi item được kiểm tra bằng cùng một Lambda. JSON payload nhỏ và mỗi item chỉ cần một state.

**Câu hỏi:** chọn chế độ nào, giới hạn concurrency ra sao?

**Gợi ý:** **Inline Map** với ItemsPath **$.items** và MaxConcurrency theo downstream (ví dụ 5). Dùng ItemSelector để truyền orderId, item và index, ResultPath để giữ kết quả. Kiểm tra total output không vượt 256 KiB.

### Tình huống C — Xử lý 500.000 dòng CSV

Đối tác đưa file 500.000 rows lên S3. Mỗi row cần chuẩn hóa và cập nhật DynamoDB; yêu cầu thống kê lỗi và tạo báo cáo cuối job.

**Câu hỏi:** Inline Map có đủ không?

**Gợi ý:** không phù hợp do dataset và execution history lớn. Dùng **Distributed Map** với ItemReader CSV, ItemBatcher khi cần, MaxConcurrency dựa trên DynamoDB capacity, ResultWriter S3, failure thresholds và job reconciliation.

### Tình huống D — 100 rows/batch, 1 row lỗi

Một child xử lý 100 rows nhưng chỉ một record sai schema làm child bị Fail. Map Run có ToleratedFailurePercentage 1%.

**Câu hỏi:** có thể kết luận chỉ 1% records lỗi không?

**Gợi ý:** không. Tolerance tính failed items/child executions theo Map Run semantics, trong khi mỗi child có thể mang cả batch. Ghi **per-row results**, tách validation lỗi vĩnh viễn khỏi transient failures và reconcile theo số record.

### Tình huống E — 10.000 Lambda đồng thời làm sập RDS

Nhóm kỹ thuật bỏ **MaxConcurrency** vì thấy Distributed Map hỗ trợ tới 10.000 child executions. Sau deploy, RDS hết connection slots và Lambda retries liên tục.

**Câu hỏi:** cần sửa lớp nào?

**Gợi ý:** giới hạn MaxConcurrency theo DB capacity, chọn batch size/connection pooling hoặc RDS Proxy phù hợp, đặt Lambda concurrency, backoff + jitter và benchmark theo p95/p99. Tăng giới hạn Step Functions không chữa RDS saturation.

### Tình huống F — Redrive làm gửi email trùng

Child gửi email thành công nhưng timeout trước khi ghi trạng thái success. Map Run thất bại, operator redrive và cùng khách hàng nhận email lần nữa.

**Câu hỏi:** Step Functions có đảm bảo exactly-once email không?

**Gợi ý:** không. Dùng idempotency/notification ledger theo jobId + recipient + template/version, lưu send status và phân biệt committed side effects với orchestration outcome. Không retry mù quáng external side effects.

### Tình huống G — ResultWriter báo lỗi

Workflow parent ở ap-southeast-1 thuộc Account A, nhưng ResultWriter trỏ bucket ở Region/account khác, role cũng thiếu PutObject.

**Câu hỏi:** nguyên nhân nào cần xem trước?

**Gợi ý:** ResultWriter S3 bucket cần cùng account và Region với state machine; phải có đúng **s3:PutObject** và KMS policy nếu encryption dùng customer-managed key. Đọc **States.ResultWriterFailed**, không tăng MaxConcurrency để sửa quyền.

### Tình huống H — JSONPath và JSONata bị trộn

Một developer copy **Parameters** và **ItemsPath** trong ví dụ JSONPath vào một state khai báo **QueryLanguage: JSONata**.

**Câu hỏi:** vì sao validation lỗi?

**Gợi ý:** JSONata dùng những trường phù hợp như **Arguments, Items** và expressions; JSONPath dùng Parameters/ItemsPath/ItemSelector với path fields theo syntax tương ứng. Chọn một kiểu cho state/definition đúng khả năng AWS hỗ trợ, validate trước deploy.

## 20. Checklist production

- [ ] Đã xác định đúng nhu cầu: **Parallel** cho branches khác chức năng; **Map** cho mỗi item.
- [ ] Đã chọn **Inline** hay **Distributed** theo input size, history events, concurrency và data source.
- [ ] Với Distributed Map, parent là **Standard**, child execution type phù hợp thời gian/semantics.
- [ ] Đã kiểm tra hard quotas **256 KiB, 25.000 events, 40 Inline, 10.000 Distributed**, và quota account/Region hiện hành.
- [ ] Đã cấu hình **ItemReader** cho dataset format/S3 path, kiểm thử schema/encoding.
- [ ] Đã kiểm tra **ItemSelector/ItemsPath/JSONPath hoặc JSONata** và input mỗi child.
- [ ] Đã đánh giá **ItemBatcher** và cách thống kê per-record failures trong mỗi batch.
- [ ] Đã đặt **MaxConcurrency** theo capacity Lambda/ECS/Batch, DB, APIs và quota.
- [ ] Đã dùng **ResultWriter** nếu output lớn và có kết quả/failed records cần lưu dài hạn.
- [ ] Đã có **Retry/Catch**, timeout, backoff/jitter và failure tolerance theo nghiệp vụ.
- [ ] Đã tách **permanent validation errors** khỏi retryable infrastructure errors.
- [ ] Đã thiết kế **idempotency keys, job ledger, compensation** cho mọi side effects.
- [ ] Đã bảo vệ State machine execution IAM role, worker roles, S3/KMS/bucket policies.
- [ ] Đã bật logs/metrics/traces cần thiết, loại PII/secrets khỏi state input/output và logs.
- [ ] Đã định nghĩa Map Run alerts, failure counters, child logs và business reconciliation.
- [ ] Đã thử S3 missing/403, KMS Deny, Lambda throttling, DB saturation, malformed CSV và output quá lớn.
- [ ] Đã thử redrive trong staging, hiểu replay semantics Standard và Express child.
- [ ] Đã có canary deployment/rollback, versioned input datasets và khả năng phục hồi sau AZ/Region incident.
- [ ] Đã tính Step Functions transitions/Express, child executions, compute, S3/KMS, logs và retries.
- [ ] Đã thống nhất điều kiện **job COMPLETED, PARTIAL, FAILED** và báo cáo audit/retention.

## 21. Ghi nhớ

**Parallel** dùng khi một workflow cần **nhiều nhánh khác nhau chạy đồng thời**, nhận input chung và tập hợp kết quả theo **thứ tự branches**. **Inline Map** dùng khi cần lặp cùng workflow qua một **JSON array nhỏ**, giới hạn tối đa 40 iterations đồng thời và chia sẻ execution history của parent. **Distributed Map** dành cho **dataset lớn**, hỗ trợ S3 **ItemReader**, batching, **ResultWriter**, **Map Run** và child executions (tối đa 10.000 đồng thời theo quota dịch vụ). Parent Distributed Map phải là **Standard**, nhưng child có thể là **Standard** hoặc **Express** trong phạm vi hỗ trợ.

Để vận hành an toàn, phải hiểu **256 KiB input/output**, **25.000 history events**, **MaxConcurrency**, **Retry/Catch**, failure tolerance, **idempotency và redrive**. Một Map Run thành công không tự đảm bảo mọi record đúng nếu lỗi đã bị Catch hoặc tolerance cho phép partial failures; cần đối soát kết quả. Mục tiêu cuối cùng là **điều phối đáng tin cậy, đúng dữ liệu, an toàn IAM/KMS, quan sát đầy đủ và chi phí phù hợp với năng lực downstream**.

### Tài liệu AWS chính thức để đối chiếu khi triển khai

- [AWS Step Functions overview](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) — giới thiệu điều phối workflow.
- [Parallel workflow state](https://docs.aws.amazon.com/step-functions/latest/dg/state-parallel.html) — branches, result array và error handling.
- [Map workflow state](https://docs.aws.amazon.com/step-functions/latest/dg/state-map.html) — chọn Inline/Distributed.
- [Inline Map state](https://docs.aws.amazon.com/step-functions/latest/dg/state-map-inline.html) — ItemsPath/ItemSelector/ItemProcessor.
- [Distributed Map state](https://docs.aws.amazon.com/step-functions/latest/dg/state-map-distributed.html) — Map Run, child workflows, concurrency và failure thresholds.
- [Map ItemReader](https://docs.aws.amazon.com/step-functions/latest/dg/input-output-itemreader.html) — CSV, JSON, JSONL, Parquet, manifests, S3 listing.
- [Map ItemBatcher](https://docs.aws.amazon.com/step-functions/latest/dg/input-output-itembatcher.html) — batching, số lượng/kích thước item.
- [Map ResultWriter](https://docs.aws.amazon.com/step-functions/latest/dg/input-output-resultwriter.html) — xuất kết quả ra S3 và IAM.
- [Map input/output processing](https://docs.aws.amazon.com/step-functions/latest/dg/input-output-fields-dist-map.html) — data transformations.
- [Choosing Standard vs Express](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html) — execution semantics và phí.
- [Redriving Map Runs](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-map-run.html) — điều kiện redrive và child replay.
- [IAM policies for Distributed Map](https://docs.aws.amazon.com/step-functions/latest/dg/iam-policies-eg-dist-map.html) — StartExecution/DescribeExecution/S3.
- [Step Functions service quotas](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html) — 256 KiB, 25.000 history events và concurrency.
- [Best practices for Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/sfn-best-practices.html) — errors, history, payload, costs.
- [AWS Step Functions pricing](https://aws.amazon.com/step-functions/pricing/) và [AWS Pricing Calculator](https://calculator.aws/) — phí theo workflow và tích hợp.



