# Glue bookmark, workflow và tối ưu tài nguyên ETL

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, AWS Glue cung cấp môi trường ETL được quản lý để khám phá dữ liệu, lập danh mục metadata và chạy pipeline xử lý dữ liệu trên Amazon S3, JDBC databases cùng nhiều nguồn/đích khác. Khi pipeline chạy theo lịch hoặc nhận dữ liệu mới liên tục, hai vấn đề vận hành thường xuất hiện: làm sao chỉ xử lý phần dữ liệu cần thiết và làm sao điều phối nhiều bước ETL với chi phí, thời gian hoàn thành có thể kiểm soát.

AWS Glue job bookmarks lưu trạng thái tiến độ đọc để hạn chế xử lý lại dữ liệu đã đọc thành công. AWS Glue workflows kết nối jobs, crawlers và triggers thành một đồ thị ETL có thể quan sát. Các cơ chế như Auto Scaling, worker types, execution class FLEX, partition pruning, file grouping và Spark tuning giúp điều chỉnh tài nguyên theo đặc tính dữ liệu.

Sau bài học, người học có thể:

- Giải thích job bookmark và phân biệt Enable, Disable, Pause, rewind và reset.
- Cấu hình bookmark cho S3 và JDBC, hiểu vai trò của bookmark keys và transformation context.
- Nhận diện các giới hạn của bookmark với dữ liệu cập nhật, xóa và target output.
- Thiết kế workflow gồm jobs, crawlers, schedule/event/conditional triggers.
- Truyền run properties giữa các bước và giới hạn số workflow run đồng thời.
- Chọn worker type, số worker, Auto Scaling và execution class phù hợp.
- Giảm lượng dữ liệu đọc bằng partition pruning, pushdown và column projection.
- Giảm overhead do small files, shuffle, skew và join.
- Theo dõi job metrics, Spark UI, workflow run và chi phí.
- Xây dựng pipeline incremental ETL có retry, backfill, idempotent output và quy trình vận hành rõ ràng.

## 1. Vai trò của bookmark, workflow và tài nguyên ETL

Một pipeline data lake thường có nhiều giai đoạn:

1. Nhận file hoặc dữ liệu từ hệ thống nguồn.
2. Phát hiện schema và cập nhật metadata trong AWS Glue Data Catalog.
3. Đọc dữ liệu mới hoặc dữ liệu cần backfill.
4. Làm sạch, chuẩn hóa và loại trùng.
5. Ghi dữ liệu vào vùng Bronze, Silver hoặc Gold.
6. Kiểm tra chất lượng, cập nhật catalog và thông báo kết quả.

Ba nhóm năng lực giải quyết các khía cạnh khác nhau:

| Năng lực | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| Job bookmark | Lần chạy tiếp theo cần đọc phần input nào? | Chỉ đọc các object S3 mới hoặc row JDBC có bookmark key lớn hơn checkpoint |
| Workflow | Bước nào chạy trước, bước nào phụ thuộc bước nào? | Crawler hoàn tất, sau đó Bronze job chạy; Bronze thành công mới chạy Silver |
| Resource optimization | Cần bao nhiêu compute và phải đọc/xử lý bao nhiêu dữ liệu? | Auto Scaling, worker G.1X, partition pruning, file grouping và tối ưu shuffle |

Các cơ chế này bổ trợ nhau. Bookmark không tự điều phối pipeline; workflow không tự bảo đảm output không trùng; tăng worker không sửa được thiết kế đọc toàn bộ dữ liệu không cần thiết. Một pipeline đáng tin cậy phải kết hợp tiến độ đọc, thứ tự thực thi, tính lặp an toàn và đo lường tài nguyên.

## 2. AWS Glue job bookmark hoạt động thế nào?

Job bookmark là trạng thái bền vững do AWS Glue lưu cho một job run. Trạng thái này giúp Glue xác định dữ liệu đầu vào nào đã được xử lý để các lần chạy sau có thể tập trung vào dữ liệu mới.

Với nguồn S3, Glue sử dụng thông tin object và thời điểm LastModified để nhận diện object cần xử lý. Với JDBC, Glue sử dụng một hoặc nhiều bookmark key để xác định row mới dựa trên giá trị key đã lưu. Bookmark có thể lưu trạng thái cho các source và transformation context trong script.

Luồng khái quát:

~~~mermaid
flowchart TD
    A[Start Glue job] --> B[job.init reads bookmark state]
    B --> C[Read supported source with transformation_ctx]
    C --> D[Filter input using saved bookmark]
    D --> E[Transform and write output]
    E --> F{All required work succeeded?}
    F -- No --> G[Job fails; bookmark is not committed]
    F -- Yes --> H[job.commit saves bookmark state]
    H --> I[Next run reads only eligible new input]
~~~

Bookmark chỉ lưu tiến độ đọc. Nó không phải transaction phân tán bao trùm source và target. Nếu job ghi được một phần output rồi lỗi trước job.commit(), lần chạy sau có thể đọc lại cùng input. Vì vậy, target cần có chiến lược ghi idempotent hoặc xử lý trùng.

Bookmark được hỗ trợ cho JDBC sources, Relationalize transform và một số S3 sources. Với Glue 1.0 trở lên, các định dạng S3 được tài liệu liệt kê gồm JSON, CSV, Apache Avro, XML, Parquet và ORC. Cần kiểm tra loại source/format và phiên bản Glue cụ thể trước khi dựa vào bookmark.

## 3. Ba chế độ bookmark: Enable, Disable và Pause

Job bookmark có ba chế độ chính:

| Chế độ | Hành vi | Khi sử dụng |
|---|---|---|
| Enable | Đọc dữ liệu mới theo bookmark và cập nhật bookmark sau lần chạy thành công | ETL incremental định kỳ |
| Disable | Không dùng bookmark; mỗi lần chạy xử lý toàn bộ phạm vi input theo script | Full refresh hoặc job tự quản lý checkpoint |
| Pause | Đọc một phạm vi incremental hoặc một khoảng run đã chỉ định nhưng không cập nhật bookmark state hiện hành | Backfill, kiểm tra lại một khoảng dữ liệu |

Disable là chế độ mặc định nếu job không được cấu hình bookmark. Enable là chế độ phổ biến cho pipeline incremental. Disable phù hợp với full reload, nhưng target cần được thay thế hoặc ghi lại theo cách tránh duplicate. Pause cho phép đọc theo run range nhưng không tiến bookmark state hiện tại.

Hai tham số dùng với Pause:

- job-bookmark-from: mốc run xác định phần input đã được xử lý trước đó và bị loại khỏi lần chạy.
- job-bookmark-to: mốc run giới hạn phần input tối đa được phép xử lý.

Khi dùng các tham số này, phải cung cấp cả from và to. Hai giá trị là job run ID, không phải ngày nghiệp vụ. Job xử lý phần input sau mốc from đến mốc to theo bookmark semantics; dữ liệu sau mốc to bị loại trừ. Hãy kiểm tra run history trước khi backfill và ghi kết quả vào target riêng hoặc một partition có thể thay thế an toàn.

Ví dụ Pause cho một khoảng run:

~~~bash
aws glue start-job-run \
  --job-name sales-incremental-etl \
  --arguments '{"--job-bookmark-option":"job-bookmark-pause","--job-bookmark-from":"jr_OLD_RUN_ID","--job-bookmark-to":"jr_NEW_RUN_ID"}' \
  --region ap-southeast-1
~~~

Ví dụ truyền bookmark option khi chạy job:

~~~bash
aws glue start-job-run \
  --job-name sales-incremental-etl \
  --arguments '{"--job-bookmark-option":"job-bookmark-enable","--run-date":"2026-11-20"}' \
  --region ap-southeast-1
~~~

Giá trị --run-date là tham số nghiệp vụ minh họa do script tự đọc; bookmark state không tự suy ra ngày nghiệp vụ từ tên tham số này.

## 4. job.init, transformation_ctx và job.commit

Khi viết Glue Spark script, cần khởi tạo job để đọc bookmark state và commit state sau khi công việc hoàn tất.

- job.init(job_name, args) lấy state hiện tại và khởi tạo bookmark service.
- transformation_ctx là định danh ổn định của source hoặc transformation context; Glue dùng nó để gắn state với đúng operator.
- job.commit() lưu state thay đổi của bookmark sau khi các thao tác cần thiết thành công.

Ví dụ S3 source:

~~~python
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

args = getResolvedOptions(sys.argv, ["JOB_NAME"])

sc = SparkContext.getOrCreate()
glue_context = GlueContext(sc)
spark = glue_context.spark_session

job = Job(glue_context)
job.init(args["JOB_NAME"], args)

source = glue_context.create_dynamic_frame.from_catalog(
    database="raw_catalog",
    table_name="sales_events",
    transformation_ctx="sales_events_source"
)

# Transform and write output here.
# Make the sink idempotent for retries and backfills.

job.commit()
~~~

Nếu thiếu job.init hoặc job.commit, bookmark không hoạt động đúng. Nếu không truyền transformation_ctx cho source DynamicFrame phù hợp, Glue không thể gắn bookmark state cho operator đó.

Giữ transformation_ctx ổn định khi source vẫn là cùng một nguồn logic. Đổi tên context hoặc thay đổi source property mà giữ context cũ có thể khiến Glue sử dụng state trước đó cho nguồn mới, dẫn đến bỏ qua dữ liệu hoặc đọc sai phạm vi. Khi cần thay nguồn, hãy đánh giá việc tạo context/job mới hoặc reset state theo quy trình có kiểm soát.

job.commit() nên nằm sau khi sink đã hoàn tất. Không gọi commit sớm trước khi write, validation hoặc publish output cần thiết hoàn thành.

## 5. Bookmark với Amazon S3

Với S3 source, Glue bookmark theo dõi object đã xử lý bằng thông tin LastModified. Ở lần chạy tiếp theo, Glue lọc các object đủ điều kiện mới hơn bookmark state.

Ví dụ cấu trúc dữ liệu:

~~~text
s3://company-data/raw/sales/
  year=2026/month=11/day=18/part-0001.json
  year=2026/month=11/day=19/part-0001.json
  year=2026/month=11/day=20/part-0001.json
~~~

Job chạy hằng ngày có thể đọc các object mới theo bookmark. Tuy nhiên:

- Bookmark S3 không phải checksum nội dung; object được ghi đè hoặc sửa sẽ có LastModified mới và có thể bị xử lý lại.
- Xóa object ở source không tạo một sự kiện xóa target tự động.
- Đổi prefix/source path có thể làm thay đổi tập input và tương tác với state cũ.
- Bookmark không xóa hoặc thay thế object ở target.
- Một file mới có timestamp cũ hơn checkpoint có thể không được nhận diện theo cách người vận hành mong đợi; cần thiết kế ingestion timestamp và backfill riêng.

Với dữ liệu được ghi bởi nhiều producer, nên dùng prefix theo ngày/giờ hoặc batch ID, tránh ghi đè object đã được xử lý. Nếu source cho phép late-arriving files, hãy định nghĩa cửa sổ backfill hoặc cơ chế kiểm tra manifest thay vì chỉ dựa vào bookmark.

### 5.1. Bookmark và partition pruning

Bookmark trả lời object nào đã được xử lý; partition pruning trả lời partition nào cần đọc trong lần chạy hiện tại. Có thể kết hợp cả hai.

Ví dụ chỉ đọc dữ liệu tháng 11:

~~~python
source = glue_context.create_dynamic_frame.from_catalog(
    database="raw_catalog",
    table_name="sales_events",
    push_down_predicate="year='2026' and month='11'",
    transformation_ctx="sales_events_source"
)
~~~

push_down_predicate lọc partition dựa trên metadata của Data Catalog trước khi Glue liệt kê object trong các partition được chọn. Với bảng có rất nhiều partition, catalogPartitionPredicate kết hợp partition index có thể giảm overhead liệt kê partition phía catalog.

Với input có số lượng object rất lớn, có thể bật AWS Glue S3 Lister bằng additional_options để giảm áp lực memory khi liệt kê file trên driver. Ví dụ:

~~~python
source = glue_context.create_dynamic_frame.from_catalog(
    database="raw_catalog",
    table_name="sales_events",
    push_down_predicate="year='2026' and month='11'",
    additional_options={"useS3ListImplementation": True},
    transformation_ctx="sales_events_source"
)
~~~

S3 Lister giúp Glue duyệt danh sách file đã lọc theo cách tiết kiệm memory hơn. Nó không thay thế partition pruning và không làm thay đổi semantics của bookmark.

Không nhầm pushdown predicate với bookmark: predicate giới hạn phạm vi đọc theo điều kiện truy vấn; bookmark lưu tiến độ giữa các lần chạy.

## 6. Bookmark với JDBC sources

Với JDBC source, Glue theo dõi một hoặc nhiều bookmark key để nhận diện row mới. Mặc định Glue có thể dùng primary key nếu giá trị tăng hoặc giảm tuần tự theo điều kiện hỗ trợ. Người dùng có thể chỉ định bookmark key và sort order trong script.

Ví dụ:

~~~python
source = glue_context.create_dynamic_frame.from_catalog(
    database="operational_db",
    table_name="orders",
    transformation_ctx="orders_jdbc_source",
    additional_options={
        "jobBookmarkKeys": ["updated_sequence"],
        "jobBookmarkKeysSortOrder": "asc"
    }
)
~~~

Bookmark key tùy chỉnh phải tăng hoặc giảm đơn điệu nghiêm ngặt. Có thể có khoảng trống trong dãy key, nhưng không nên dùng cột có giá trị được tái sử dụng hoặc quay ngược như trạng thái, loại đơn hàng hay revision number không đơn điệu.

Một giới hạn quan trọng: JDBC bookmark không tự phát hiện UPDATE trên row đã có key nhỏ hơn hoặc bằng checkpoint. Nếu một row cũ thay đổi nhưng bookmark key không tăng, job có thể không đọc lại row đó. Bookmark cũng không phải CDC transaction-log capture. Với yêu cầu đồng bộ insert/update/delete, hãy xem xét AWS DMS CDC, timestamp/change sequence được quản lý đúng, hoặc chiến lược full reconciliation.

Nếu nguồn dùng updated_at làm bookmark key, phải bảo đảm giá trị này tăng đơn điệu theo dữ liệu cần đọc và không bị cập nhật lùi. Trong thực tế, timestamp có thể trùng hoặc bị clock skew; một compound key có thể cần kết hợp sequence duy nhất. Hãy kiểm tra logic key với dữ liệu thực tế và các trường hợp transaction commit trễ.

## 7. Rewind, reset và backfill bookmark

Glue hỗ trợ rewind bookmark của Spark ETL job về một lần chạy trước hoặc reset toàn bộ bookmark state.

| Thao tác | Kết quả | Cảnh báo |
|---|---|---|
| Rewind | Đưa bookmark về trạng thái của run trước đó để xử lý lại input từ mốc đó | Các output đã ghi không tự bị xóa |
| Reset | Xóa bookmark state để job có thể đọc lại toàn bộ input hỗ trợ | Có thể tạo duplicate nếu target không được dọn hoặc thay thế |
| Pause với from/to | Chạy một khoảng input nhưng không cập nhật bookmark state hiện hành | Phải quản lý output của lần chạy backfill |

Reset bookmark:

~~~bash
aws glue reset-job-bookmark \
  --job-name sales-incremental-etl \
  --region ap-southeast-1
~~~

Reset không dọn output ở S3, database hoặc các target khác. Glue chỉ theo dõi tiến độ input qua bookmark; target không được bookmark tự động rollback. Vì vậy, trước khi reset hoặc rewind:

1. Xác định run ID và phạm vi dữ liệu cần xử lý lại.
2. Xác định output partition hoặc target rows bị ảnh hưởng.
3. Chọn overwrite partition, staging prefix, merge/upsert hoặc dedup theo business key.
4. Lưu snapshot hoặc version output cần thiết để rollback.
5. Thực hiện backfill và xác minh số liệu.
6. Chỉ đưa kết quả vào vùng phục vụ khi validation thành công.

Nếu cần replay thường xuyên, cân nhắc tách job backfill khỏi job incremental production. Cách này tránh việc reset bookmark của job production làm thay đổi checkpoint đang dùng.

Bookmark state được quản lý theo job. Nếu xóa Glue job, bookmark state của job đó cũng bị xóa; tạo lại job cùng tên không khôi phục state cũ. Hãy lưu run history và kế hoạch backfill trước khi xóa hoặc thay thế job production.

## 8. Output idempotency và cửa sổ lỗi

Bookmark và sink write không nằm trong một transaction phân tán. Ví dụ:

1. Job đọc file A.
2. Job ghi thành công một phần dữ liệu vào target.
3. Job gặp lỗi trước job.commit().
4. Lần chạy sau bookmark chưa được cập nhật nên file A được đọc lại.

Nếu sink append toàn bộ record, target có thể có dữ liệu trùng. Một pipeline cần thiết kế output idempotent theo một trong các cách:

- Ghi đè partition xác định bởi business date hoặc batch ID.
- Ghi vào staging prefix, validation xong mới publish/commit metadata.
- Dùng merge/upsert theo business key và version.
- Ghi event ID rồi deduplicate ở downstream.
- Lưu manifest các batch đã publish để chống xử lý lặp.

Ví dụ ghi output theo ngày:

~~~python
from datetime import date

run_date = date.today().isoformat()
target_path = f"s3://company-data/curated/sales/run_date={run_date}/"

# The pipeline should replace or publish this partition idempotently.
# Do not blindly append duplicate rows on every retry.
~~~

Cần phân biệt retry cùng một job run với một lần backfill có chủ đích. Nếu hai run đồng thời ghi cùng partition, chúng có thể ghi đè hoặc tạo trạng thái không nhất quán. Dùng workflow/job concurrency, lock nghiệp vụ hoặc partition ownership để tránh xung đột.

## 9. AWS Glue workflows: điều phối pipeline

Workflow là tập hợp jobs, crawlers và triggers phụ thuộc nhau. Nó biểu diễn pipeline thành đồ thị có hướng, ghi nhận trạng thái thực thi và cho phép quan sát tiến độ toàn luồng.

Ví dụ:

~~~mermaid
flowchart TD
    A[EventBridge S3 arrival or schedule] --> B[Workflow start trigger]
    B --> C[Raw catalog crawler]
    C --> D{Crawler succeeded}
    D --> E[Bronze ETL job]
    E --> F{Bronze succeeded}
    F --> G[Silver ETL job]
    G --> H{Silver succeeded}
    H --> I[Quality check job]
    I --> J[Publish curated data]
~~~

Các thành phần:

- Job: chạy ETL script, Spark, Python shell hoặc loại workload Glue được hỗ trợ.
- Crawler: khám phá schema và cập nhật metadata trong Data Catalog.
- Trigger: bắt đầu job/crawler theo lịch, theo yêu cầu, theo event hoặc theo điều kiện hoàn tất.
- Workflow run: một lần thực thi toàn đồ thị.
- Workflow run properties: cặp key/value dùng để truyền state hoặc tham số giữa các bước.

Workflow có static view mô tả thiết kế và dynamic view mô tả trạng thái thực tế của lần chạy, bao gồm component đã hoàn tất, đang chạy hoặc lỗi.

## 10. Các loại trigger trong workflow

Có ba loại start trigger chính:

| Trigger | Cách bắt đầu | Ví dụ |
|---|---|---|
| Schedule | Theo lịch hoặc cron expression | Chạy ETL mỗi ngày lúc 01:00 UTC |
| On demand | Người vận hành gọi console, API hoặc CLI | Chạy backfill theo yêu cầu |
| EventBridge event | Khi nhận event hoặc batch event | Có object mới trong S3 |

Conditional trigger bên trong workflow có thể bắt đầu job hoặc crawler khi một hay nhiều điều kiện về trạng thái component được thỏa mãn. Ví dụ Silver job chỉ chạy khi Bronze job thành công và crawler đã cập nhật catalog. Conditions có thể được kết hợp bằng logic AND/OR tùy cấu hình trigger.

EventBridge event trigger có thể gom nhiều event trước khi khởi chạy workflow. Có thể cấu hình batch size và batch window; batch window tối đa 900 giây (15 phút). Điều kiện đạt trước sẽ khởi chạy workflow. Nếu không cấu hình batch conditions, batch size mặc định là 1.

Một số giới hạn vận hành cần nhớ:

- Một workflow nên có tối đa 100 jobs, crawlers và triggers cộng lại.
- Có thể đặt MaxConcurrentRuns để ngăn nhiều workflow run cập nhật cùng dữ liệu đồng thời.
- Nếu vượt concurrency limit, workflow run không được bắt đầu dù event condition đã thỏa mãn; AWS Glue không tự retry workflow run bị từ chối vì vượt giới hạn.
- Nếu event/batch đã kích hoạt một workflow run nhưng run đó thất bại, event/batch đó không được dùng lại để tự khởi chạy run mới; workflow chờ event/batch tiếp theo.
- Cần có cơ chế redrive hoặc phát lại event có kiểm soát nếu pipeline cần retry từ cùng input.

Không nên đặt concurrency bằng 1 cho mọi workflow theo thói quen. Hãy chọn dựa trên việc các run có thể ghi các partition độc lập hay có nguy cơ cập nhật cùng target.

## 11. Workflow run properties và truyền tham số

Workflow run properties là map key/value được chia sẻ giữa các jobs trong cùng workflow run. Chúng hữu ích để truyền source path, batch ID, partition date, schema version hoặc run mode.

Ví dụ workflow có property:

~~~json
{
  "source_prefix": "s3://company-data/raw/sales/batch=2026-11-20/",
  "business_date": "2026-11-20",
  "run_mode": "incremental",
  "schema_version": "3"
}
~~~

Job có thể đọc workflow name và run ID từ arguments, sau đó gọi Glue API GetWorkflowRunProperties để lấy properties. Một job có thể dùng PutWorkflowRunProperties để cập nhật giá trị cho các bước chạy sau.

Ví dụ Python:

~~~python
import sys
import boto3

from awsglue.utils import getResolvedOptions

args = getResolvedOptions(
    sys.argv,
    ["JOB_NAME", "WORKFLOW_NAME", "WORKFLOW_RUN_ID"]
)

glue = boto3.client("glue")

response = glue.get_workflow_run_properties(
    Name=args["WORKFLOW_NAME"],
    RunId=args["WORKFLOW_RUN_ID"]
)

run_properties = response["RunProperties"]
source_prefix = run_properties["source_prefix"]
business_date = run_properties["business_date"]

print(f"Processing {source_prefix} for {business_date}")
~~~

Không lưu plaintext secrets trong workflow run properties vì properties có thể xuất hiện trong log hoặc được nhiều component đọc. Dùng Glue Connection, Secrets Manager hoặc cơ chế quản lý secret phù hợp. Workflow properties cũng không phải kho lưu state bền vững thay cho database; chúng phù hợp với tham số điều phối trong một run.

## 12. Thiết kế workflow cho data lake nhiều tầng

Một pipeline Bronze/Silver/Gold có thể tổ chức như sau:

| Tầng | Nhiệm vụ | Input/Output |
|---|---|---|
| Landing/Raw | Nhận file gốc, giữ schema và metadata nguồn | Producer -> S3 raw |
| Bronze | Chuẩn hóa encoding, schema cơ bản, thêm ingestion metadata | S3 raw -> S3 bronze |
| Silver | Làm sạch, deduplicate, join và chuẩn hóa business entities | Bronze -> S3 silver |
| Gold | Tạo aggregate, fact/dimension và dataset phục vụ BI | Silver -> S3 gold |
| Catalog/Quality | Cập nhật Data Catalog và kiểm tra chất lượng | Catalog, quality results |

Workflow nên chia component theo ranh giới lỗi và quyền sở hữu dữ liệu. Một job quá lớn khó retry từng bước; quá nhiều job nhỏ lại tăng startup overhead và chi phí điều phối.

Một thiết kế tốt:

- Trigger nhận event hoặc schedule ở đầu pipeline.
- Crawler chỉ chạy khi schema discovery thực sự cần thiết; không nhất thiết chạy mọi batch nếu schema ổn định.
- Bronze job dùng bookmark hoặc manifest để nhận input incremental.
- Silver job chạy sau khi Bronze hoàn tất và publish thành công.
- Quality job kiểm tra count, null, uniqueness và business invariants.
- Gold job chỉ nhận partition đã được xác nhận.
- Workflow properties truyền batch ID và ngày nghiệp vụ xuyên suốt.
- MaxConcurrentRuns và job MaxConcurrentRuns bảo vệ target khỏi ghi đè đồng thời.
- EventBridge/SNS hoặc hệ thống ticket nhận thông báo khi workflow thất bại.

## 13. Worker types và DPU

AWS Glue Spark job chạy trên các worker được định nghĩa trước. Worker type quyết định số DPU, vCPU, memory và disk của mỗi worker.

Một số worker phổ biến:

| Worker type | DPU/M-DPU | vCPU | Memory | Đặc điểm |
|---|---:|---:|---:|---|
| G.1X | 1 | 4 | 16 GB | Workload ETL thông thường |
| G.2X | 2 | 8 | 32 GB | Dataset/join lớn hơn |
| G.4X | 4 | 16 | 64 GB | Transform, aggregate và join nặng |
| G.8X | 8 | 32 | 128 GB | Workload lớn, cần compute/memory cao |
| G.12X | 12 | 48 | 192 GB | Workload rất lớn, phụ thuộc Region/Glue version |
| G.16X | 16 | 64 | 256 GB | Workload rất lớn, phụ thuộc Region/Glue version |
| R.1X | 1 | 4 | 32 GB | Memory-optimized |
| R.2X | 2 | 8 | 64 GB | Memory-optimized |
| R.4X | 4 | 16 | 128 GB | Memory-optimized |
| R.8X | 8 | 32 | 256 GB | Memory-optimized |

R workers có tỷ lệ memory/vCPU cao hơn G workers, phù hợp workload cache, aggregation, join hoặc shuffle thường gặp OOM. Không nên chọn R worker chỉ vì dataset lớn; hãy xác định memory pressure thực sự qua executor metrics và Spark UI.

G.025X có 0,25 DPU, 2 vCPU và 4 GB memory, chủ yếu dành cho Glue streaming jobs với tải thấp; không dùng nó làm lựa chọn chung cho batch Spark ETL.

G.12X, G.16X và R worker có điều kiện hỗ trợ theo Glue version và Region. Hãy xác minh availability trước khi thiết kế workflow production. Worker lớn có thể có startup latency cao hơn; tăng kích thước không đảm bảo job nhanh hơn nếu bottleneck nằm ở S3 listing, shuffle, JDBC throughput hoặc một task bị skew.

## 14. AWS Glue Auto Scaling

Auto Scaling cho phép Glue tự tăng/giảm số worker theo mức song song ở các stage hoặc micro-batch. Người vận hành đặt worker type và giới hạn worker tối đa; Glue quyết định số worker cần cấp trong phạm vi đó.

Auto Scaling hỗ trợ AWS Glue version 3.0 trở lên cho ETL, interactive sessions và streaming jobs. Các worker type hỗ trợ gồm G.1X, G.2X, G.4X, G.8X, G.12X, G.16X, R.1X, R.2X, R.4X, R.8X; G.025X chỉ dành cho streaming jobs. Standard DPUs không hỗ trợ Auto Scaling.

Bật Auto Scaling trong job arguments:

~~~json
{
  "JobName": "sales-silver-etl",
  "Arguments": {
    "--enable-auto-scaling": "true",
    "--enable-metrics": "true"
  },
  "WorkerType": "G.2X",
  "NumberOfWorkers": 20
}
~~~

Trong ví dụ, NumberOfWorkers được dùng làm giới hạn worker tối đa khi Auto Scaling được bật. Hãy xác minh cấu hình cụ thể của job qua Glue version và API đang dùng.

Auto Scaling hữu ích khi workload có các stage khác nhau về độ song song: đọc nhiều file có thể cần nhiều worker, một stage join hoặc output có thể cần ít hơn. Tuy nhiên, Auto Scaling không sửa được một task đơn lẻ bị skew hoặc một partition quá lớn. Nếu chỉ một executor làm việc trong khi phần còn lại idle, hãy xem lại partitioning, skew và query plan.

Theo dõi worker utilization, executor metrics, DPUSeconds, stage duration và Spark UI để xác nhận Auto Scaling thực sự giảm thời gian hoặc chi phí. Không chỉ so sánh số worker tối đa giữa hai lần chạy.

## 15. Execution class FLEX

AWS Glue hỗ trợ execution class STANDARD và FLEX cho một số Glue Spark jobs.

- STANDARD: ưu tiên khởi chạy và hoàn thành ổn định hơn cho workload cần thời gian thực thi dễ dự đoán.
- FLEX: tối ưu chi phí cho workload có thể chờ capacity và chấp nhận thời gian khởi chạy/hoàn tất linh hoạt.

FLEX được hỗ trợ cho Spark ETL jobs (command type glueetl) trên Glue 3.0 trở lên với worker type G.1X hoặc G.2X. Các worker type mới như G.12X, G.16X và R.1X–R.8X không hỗ trợ FLEX theo tài liệu job properties hiện hành.

FLEX phù hợp với:

- Backfill không cần hoàn tất ngay.
- Batch theo ngày có SLA rộng.
- Tác vụ phát sinh khi có capacity.
- Workload có thể retry hoặc chạy lại mà không ảnh hưởng dữ liệu.

Không dùng FLEX cho pipeline có cutover time cứng, SLA ngắn hoặc dependency downstream cần kết quả ngay. Nếu workflow có nhiều job nối tiếp và một job FLEX khởi chạy chậm, toàn bộ pipeline có thể bị kéo dài.

FLEX thay đổi cách tính phí theo số worker và thời gian mỗi worker thực sự chạy; cần dùng AWS pricing và job run metrics hiện hành để so sánh tổng chi phí, không chỉ nhìn execution duration.

## 16. Giảm lượng dữ liệu phải đọc

Tối ưu hiệu quả nhất thường là tránh đọc dữ liệu không cần thiết. Trước khi tăng worker, hãy kiểm tra input scan.

### 16.1. Partition pruning và pushdown

Nếu S3 dataset được partition theo year, month, day, hãy lọc ngay từ Data Catalog thay vì đọc mọi file rồi filter trong Spark.

~~~python
source = glue_context.create_dynamic_frame.from_catalog(
    database="raw_catalog",
    table_name="clickstream",
    push_down_predicate="year='2026' and month='11' and day='20'",
    transformation_ctx="clickstream_source"
)
~~~

push_down_predicate giúp Glue chỉ liệt kê và đọc các partition phù hợp. Với bảng có số lượng partition rất lớn, catalogPartitionPredicate kết hợp partition index cho phép server-side filtering trong Data Catalog và giảm overhead liệt kê.

### 16.2. Projection và predicate pushdown

Chỉ đọc các cột cần dùng. Parquet và ORC là columnar formats, có thể giảm I/O nhờ projection và predicate pushdown.

~~~python
df = spark.read.parquet("s3://company-data/silver/sales/")
filtered = (
    df.select("order_id", "customer_id", "order_date", "total_amount")
      .where("order_date >= DATE '2026-11-01'")
)
~~~

Filter sớm trước join và aggregation giúp giảm dữ liệu shuffle. Dùng Parquet/ORC với compression phù hợp cho analytical workloads; chọn schema và partition layout dựa trên query patterns thực tế.

## 17. Small files, grouping và output compaction

Quá nhiều file nhỏ gây overhead khi liệt kê S3 objects, tạo Spark tasks và lập kế hoạch thực thi. Một dataset 100 GB gồm hàng triệu file vài KB có thể chậm hơn dataset cùng dung lượng gồm file có kích thước hợp lý.

Với một số S3 input formats, Glue hỗ trợ file grouping:

- groupFiles = "inPartition" để nhóm file trong từng partition.
- groupSize đặt kích thước nhóm mong muốn theo byte.
- Glue tự bật grouping trong một số trường hợp có hơn 50.000 input files.
- Tính năng grouping hỗ trợ CSV, Ion, GrokLog, JSON và XML; không hỗ trợ Avro, Parquet hoặc ORC theo tài liệu hiện hành.

Ví dụ:

~~~python
source = glue_context.create_dynamic_frame.from_options(
    connection_type="s3",
    connection_options={
        "paths": ["s3://company-data/raw/events/"],
        "recurse": True,
        "groupFiles": "inPartition",
        "groupSize": "134217728"
    },
    format="json",
    transformation_ctx="raw_events_source"
)
~~~

Ví dụ groupSize là 128 MiB. Hãy chọn theo kích thước dữ liệu, số executor và format; không áp dụng máy móc cho mọi pipeline.

Ở output, có thể dùng repartition() hoặc coalesce() để điều chỉnh số file. coalesce(1) thường tạo một bottleneck và file quá lớn cho workload phân tán. Chọn số partition theo dung lượng, parallelism và query pattern. Có thể chạy compaction job định kỳ để hợp nhất small files trong data lake.

## 18. Tối ưu shuffle, join và data skew

Shuffle xảy ra khi Spark phải trao đổi dữ liệu giữa executors, thường do join, groupBy, distinct, repartition hoặc sort. Shuffle có thể tiêu tốn network, disk và memory.

Các nguyên tắc:

- Filter và project sớm trước wide transformations.
- Broadcast bảng dimension nhỏ nếu kích thước phù hợp với memory của executors.
- Repartition theo join key khi cần phân bố dữ liệu và giảm shuffle lặp.
- Tránh sort hoặc distinct không cần thiết.
- Kiểm tra skew khi một số key chiếm phần lớn record.
- Dùng Spark UI để tìm stage có task chạy lâu bất thường, spill hoặc shuffle read/write lớn.
- Chọn partition count dựa trên số worker, data size và task duration.

Data skew xảy ra khi một key có nhiều dữ liệu hơn hẳn các key khác. Một vài task có thể chạy rất lâu trong khi phần lớn executors đã idle. Tăng worker không nhất thiết giải quyết; cần xem xét salting key, tách hot key, broadcast join hoặc chiến lược aggregation hai giai đoạn. Salting thay đổi cách phân nhóm nên phải bảo đảm kết quả cuối cùng vẫn đúng.

Với Glue Spark jobs, dùng Spark UI và event logs để hiểu DAG, stages, task distribution, executor memory và shuffle spill. Hãy đo trước/sau khi thay đổi một tham số để biết cải thiện đến từ đâu.

## 19. Đo lường và tối ưu theo số liệu

AWS khuyến nghị quy trình tuning theo vòng lặp:

1. Xác định mục tiêu: SLA, chi phí, throughput hoặc độ ổn định.
2. Đo baseline qua Glue metrics, CloudWatch logs và Spark UI.
3. Xác định bottleneck: scan, planning, shuffle, CPU, memory, I/O hay downstream.
4. Chọn một thay đổi phù hợp.
5. Chạy lại với dữ liệu đại diện và so sánh.
6. Lặp lại cho tới khi đạt mục tiêu.

Các chỉ số nên quan sát:

| Nhóm | Chỉ số/dấu hiệu | Cách diễn giải |
|---|---|---|
| Job | Duration, DPUSeconds, retries, failed runs | Thời gian và tài nguyên thực dùng |
| Worker | Worker utilization, executor count, memory | Xác định over-provision hoặc thiếu tài nguyên |
| Spark | Stage duration, task skew, shuffle read/write, spill | Tìm bottleneck xử lý |
| Source | Bytes scanned, files listed, JDBC read throughput | Phát hiện đọc quá nhiều hoặc source chậm |
| Sink | Write throughput, small files, commit latency | Phát hiện output bottleneck |
| Bookmark | Input range, run state, commit success | Xác nhận tiến độ incremental |
| Workflow | Run duration, component state, concurrency rejection | Xác định bước làm chậm hoặc bị chặn |

Bật Glue job metrics và observability metrics theo nhu cầu. Có thể bật Spark UI event logs để phân tích chi tiết DAG. Log và metrics nên giữ đủ lâu cho điều tra, nhưng cần kiểm soát chi phí và tránh ghi dữ liệu nhạy cảm.

## 20. Quản lý concurrency, retry và chi phí

Một workflow có thể chạy đồng thời nhiều lần nếu không giới hạn. Điều này có thể làm hai job ghi cùng partition, dùng quá nhiều worker hoặc tạo race condition với bookmark.

Cần kiểm soát ở hai cấp:

- MaxConcurrentRuns của workflow giới hạn số workflow run cùng lúc.
- MaxConcurrentRuns của từng job giới hạn số job run đồng thời.

Đối với job bookmark có cùng source và target state, thường nên giới hạn concurrent run hoặc thiết kế partition ownership để không có hai run cùng cập nhật một vùng dữ liệu.

Glue job có thể cấu hình retry count. Retry chỉ hữu ích khi lỗi tạm thời và output có thể retry an toàn. Với lỗi schema, permission hoặc dữ liệu không hợp lệ, retry nhiều lần chỉ tăng chi phí. Đặt timeout hợp lý; Glue job timeout tối đa 7 ngày (10.080 phút), nhưng default phụ thuộc Glue version. Đừng để job treo kéo dài mà không có cảnh báo.

Các biện pháp kiểm soát chi phí:

- Dùng bookmark để tránh đọc lại dữ liệu đã xử lý thành công.
- Dùng partition pruning, projection và predicate pushdown để giảm scan.
- Dùng Auto Scaling với max worker hợp lý.
- Dùng FLEX cho batch có SLA linh hoạt và worker type được hỗ trợ.
- Tránh crawler chạy không cần thiết.
- Hạn chế workflow/job concurrency khi target không hỗ trợ ghi đồng thời.
- Dọn log, temporary files và staging data theo lifecycle.
- Compaction để giảm small files và chi phí truy vấn downstream.
- Tối ưu retry và timeout để không trả tiền cho lần chạy chắc chắn thất bại.

Không giảm worker count trước khi hiểu job đang chờ I/O hay compute. Một job nhỏ hơn nhưng chạy lâu gấp nhiều lần có thể đắt hơn.

## 21. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Job đọc lại file cũ | Bookmark không bật, thiếu transformation_ctx, đổi source/context hoặc object LastModified thay đổi | Kiểm tra job args, context và source path |
| JDBC bỏ sót row mới | Bookmark key không tăng đơn điệu hoặc transaction commit trễ | Kiểm tra key semantics, chọn sequence/timestamp phù hợp và backfill |
| JDBC không đọc UPDATE | Bookmark không theo dõi thay đổi của row cũ | Dùng CDC hoặc reconciliation |
| Job thành công nhưng target bị trùng | Output append; lần chạy trước ghi một phần rồi lỗi trước job.commit() | Thiết kế sink idempotent, overwrite partition hoặc merge |
| Reset bookmark nhưng target vẫn có dữ liệu cũ | Bookmark không quản lý output cleanup | Dọn hoặc thay thế target theo runbook riêng |
| Workflow không khởi chạy | Trigger sai, concurrency limit hoặc event pattern không khớp | Kiểm tra trigger state, batch condition và workflow run history |
| Workflow run thất bại nhưng không tự retry | Event/batch đã tiêu thụ hoặc concurrency rejection | Redrive/phát lại event theo cơ chế riêng |
| Worker bị OOM | Join/shuffle lớn, skew hoặc cache quá nhiều | Kiểm tra Spark UI; giảm data scan, xử lý skew hoặc chọn R worker |
| Nhiều worker idle | Ít partition hoặc một stage tuần tự | Tăng parallelism hợp lý, repartition hoặc chia nhỏ workload |
| Job chậm do small files | Quá nhiều object/task nhỏ | Group input nếu format hỗ trợ, compaction output |
| Glue tốn chi phí cao | Quá nhiều worker, thời gian chạy dài, retry/crawler thừa | Đo DPUSeconds, Auto Scaling, FLEX và giảm data scan |
| Bookmark state bị sai sau đổi script | Đổi transformation_ctx hoặc source mapping | Review state, dùng context ổn định hoặc backfill/reset có kiểm soát |

## 22. Thực hành: pipeline sales incremental trên S3

Một doanh nghiệp nhận file sales mỗi ngày vào s3://company-data/raw/sales/. Pipeline cần xử lý file mới, chuẩn hóa schema, ghi Silver theo ngày và tạo Gold aggregate. Mỗi lần chạy không được nhân đôi dữ liệu nếu job retry.

### Thiết kế

| Thành phần | Cấu hình |
|---|---|
| Source | S3 raw sales partitioned by year/month/day |
| Bronze job | Glue Spark job, bookmark Enable, stable transformation context |
| Silver job | Deduplicate theo event/order ID, ghi partition theo business date |
| Gold job | Aggregate doanh thu theo ngày và khu vực |
| Trigger | EventBridge khi object đến hoặc schedule hằng ngày |
| Workflow | Bronze thành công -> Silver -> Quality check -> Gold |
| Resource | Bắt đầu G.1X/G.2X; Auto Scaling nếu workload thay đổi |
| Backfill | Job riêng hoặc Pause/rewind theo run ID |
| Monitoring | Job metrics, workflow graph, DPUSeconds, output counts |

### Các bước triển khai

1. Tạo Glue Data Catalog database và table cho raw sales.
2. Tạo Bronze job với bookmark Enable và transformation_ctx="sales_raw_source".
3. Đọc partition cần thiết bằng push_down_predicate.
4. Chuẩn hóa schema và thêm ingestion_date, source_file và event_id.
5. Ghi Bronze/Silver theo batch ID hoặc partition có thể overwrite idempotently.
6. Chỉ gọi job.commit() sau khi sink write và validation thành công.
7. Tạo workflow gồm start trigger, Bronze, Silver, quality job và Gold.
8. Truyền business_date và batch_id qua workflow run properties.
9. Đặt concurrency phù hợp để không có hai run ghi cùng partition.
10. Bật Auto Scaling với maximum worker được đo bằng thử nghiệm.
11. Bật CloudWatch metrics và Spark UI để tìm bottleneck.
12. Thử chạy lại cùng input; xác nhận bookmark không đọc lại file cũ và output không trùng.
13. Thử một file late-arriving và một object bị sửa; xác nhận quy trình backfill xử lý đúng.
14. Thử reset/rewind trên môi trường kiểm thử; xác nhận target được quản lý độc lập với bookmark.
15. Diễn tập workflow failure và redrive event; xác nhận pipeline phục hồi mà không mất batch.

### Tiêu chí thành công

- Job chỉ đọc input thuộc phạm vi incremental dự kiến.
- Bookmark được commit sau khi output hoàn tất.
- Retry không tạo duplicate trong target.
- Workflow chỉ chạy component downstream khi dependency thành công.
- Workflow concurrency không làm hai run ghi cùng partition.
- Auto Scaling không vượt maximum worker đã cấu hình.
- Spark UI và CloudWatch metrics cho thấy bottleneck đã được xác định.
- Backfill không làm thay đổi checkpoint production ngoài kế hoạch.
- Gold output được kiểm tra bằng tổng doanh thu, số đơn và số bản ghi.

## Kết luận

AWS Glue job bookmarks lưu tiến độ đọc để hỗ trợ ETL incremental. S3 bookmark dựa trên LastModified của object; JDBC bookmark dựa trên bookmark keys và không tự phát hiện mọi UPDATE/DELETE. job.init, transformation_ctx ổn định và job.commit đúng thời điểm là điều kiện quan trọng. Reset hoặc rewind chỉ thay đổi bookmark state, không dọn output đã ghi.

AWS Glue workflows điều phối jobs, crawlers và triggers theo schedule, on-demand, EventBridge hoặc điều kiện hoàn tất. Run properties truyền tham số giữa các bước; concurrency limit giúp bảo vệ target và kiểm soát chi phí. Tuy nhiên, event hoặc workflow run bị từ chối/thất bại cần cơ chế redrive rõ ràng.

Tối ưu ETL bắt đầu bằng việc giảm dữ liệu phải đọc, giảm small files và shuffle, rồi mới điều chỉnh worker. Auto Scaling, G/R worker types và FLEX có các điều kiện hỗ trợ riêng. Hãy đo bằng Glue metrics, CloudWatch và Spark UI trước khi thay đổi cấu hình. Một pipeline production cần kết hợp bookmark, output idempotency, workflow orchestration, monitoring và runbook backfill/retry.

## Tài liệu tham khảo

- [Tracking processed data using job bookmarks](https://docs.aws.amazon.com/glue/latest/dg/monitor-continuations.html)
- [Using job bookmarks in AWS Glue scripts](https://docs.aws.amazon.com/glue/latest/dg/programming-etl-connect-bookmarks.html)
- [Troubleshooting Glue bookmark and transformation context errors](https://docs.aws.amazon.com/glue/latest/dg/glue-troubleshooting-errors.html)
- [Overview of workflows in AWS Glue](https://docs.aws.amazon.com/glue/latest/dg/workflows_overview.html)
- [Creating and building out workflows manually](https://docs.aws.amazon.com/glue/latest/dg/creating_running_workflows.html)
- [AWS Glue workflows API](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-api-workflow.html)
- [Getting and setting workflow run properties](https://docs.aws.amazon.com/glue/latest/dg/workflow-run-properties-code.html)
- [Using Auto Scaling for AWS Glue](https://docs.aws.amazon.com/glue/latest/dg/auto-scaling.html)
- [AWS Glue worker types](https://docs.aws.amazon.com/glue/latest/dg/worker-types.html)
- [Configuring job properties for Spark jobs](https://docs.aws.amazon.com/glue/latest/dg/add-job.html)
- [AWS Glue job runs and execution class](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-api-jobs-runs.html)
- [Managing partitions for ETL output](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-partitions.html)
- [Optimizing reads with pushdown in AWS Glue ETL](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-pushdown.html)
- [Reading input files in larger groups](https://docs.aws.amazon.com/glue/latest/dg/grouping-input-files.html)
- [Connection options and the AWS Glue S3 Lister](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-connect.html)
- [Improving performance for AWS Glue Spark jobs](https://docs.aws.amazon.com/glue/latest/dg/tuning-aws-glue-for-apache-spark.html)
- [Best practices for performance tuning AWS Glue for Apache Spark jobs](https://docs.aws.amazon.com/prescriptive-guidance/latest/tuning-aws-glue-for-apache-spark/introduction.html)
- [Strategies for tuning Spark job performance](https://docs.aws.amazon.com/prescriptive-guidance/latest/tuning-aws-glue-for-apache-spark/performance-tuning-strategies.html)
- [AWS Glue pricing](https://aws.amazon.com/glue/pricing/)

