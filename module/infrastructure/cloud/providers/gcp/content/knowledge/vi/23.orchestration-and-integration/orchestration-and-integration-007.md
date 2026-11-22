# Cloud Scheduler và thực thi tác vụ theo lịch

> **Chương:** Điều phối và tích hợp ứng dụng  
> **Bài học:** Cloud Scheduler và thực thi tác vụ theo lịch  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học làm quen Google Cloud từ quản trị project, IAM, VPC tới Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, đồng thời học cách tự động hóa phát hành, theo dõi độ tin cậy và chi phí. Một yêu cầu vận hành lặp lại là **chạy công việc theo lịch**: tạo báo cáo cuối ngày, đồng bộ danh mục mỗi giờ, dọn dữ liệu hết hạn hoặc khởi động batch Java vào ban đêm.

**Cloud Scheduler** là dịch vụ cron được quản lý: nó **gửi yêu cầu vào thời điểm được cấu hình**, còn nơi nhận chịu trách nhiệm **thực hiện công việc**. Target có thể là **HTTP/S endpoint**, **Pub/Sub topic** hoặc **App Engine HTTP application**. Để chạy Java batch nhiều bước, có thể kết hợp Scheduler với **Cloud Run Jobs, Workflows hoặc một subscriber**. Dịch vụ không tự cấp CPU/RAM để chạy mã Java hay thay thế hệ quản trị workflow.

Điểm quan trọng nhất: Cloud Scheduler có **at-least-once delivery**. Khi request timeout hoặc phản hồi thất lạc, cùng một kỳ lịch có thể được gửi nhiều lần. Vì vậy, tác vụ ảnh hưởng tiền, tồn kho hoặc dữ liệu phải **idempotent** — chạy lại không tạo side effect ngoài ý muốn. Ví dụ và lệnh trong bài dùng tài nguyên giả định; chỉ chạy trong sandbox được phê duyệt vì có thể tạo dịch vụ, thay IAM và phát sinh phí.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Cloud Scheduler** (định giờ/kích hoạt) với **Cloud Run service**, **Cloud Run Job**, **Pub/Sub**, **Cloud Tasks** và **Workflows** (thực thi hoặc điều phối).
2. Viết lịch **unix-cron 5 trường** và dùng múi giờ IANA, tránh lỗi daylight saving time (DST).
3. Chọn target **HTTP**, **Pub/Sub** hoặc **App Engine** đúng kiến trúc.
4. Thiết lập **OIDC service account** để Scheduler gọi **private Cloud Run service**, dùng **OAuth** khi gọi Google APIs `*.googleapis.com`.
5. Cấu hình HTTP **attempt deadline**, retry count, backoff; hiểu giới hạn và tác động lên các kỳ lịch kế tiếp.
6. Dùng **job name + schedule time** làm idempotency key, xác nhận bằng transaction/unique constraint trong Java.
7. Tạo, đọc, chạy thử, pause/resume, cập nhật và xóa job bằng `gcloud`.
8. Tích hợp Scheduler với **Pub/Sub**, **Cloud Run Jobs** hoặc **Workflows** cho tác vụ dài/phức tạp.
9. Giám sát failures, latency, executions bị bỏ qua và chi phí; viết runbook an toàn.
10. Hoàn thành bài tập thiết kế lịch, xử lý trùng và chọn dịch vụ.

## 2. Mô hình hoạt động: trigger không phải worker

~~~mermaid
flowchart LR
    S["Cloud Scheduler<br/>cron + timezone + retry"]
    H["HTTP target<br/>Cloud Run Java service"]
    P["Pub/Sub topic"]
    Q["Java subscriber<br/>GKE/Compute Engine"]
    J["Cloud Run Jobs API<br/>Java batch execution"]
    W["Workflows API<br/>nhiều bước"]
    DB["Cloud SQL / Cloud Storage"]
    S -->|"OIDC HTTP"| H
    S -->|"Publish"| P
    P --> Q
    S -->|"OAuth HTTP"| J
    S -->|"OAuth HTTP"| W
    H --> DB
    Q --> DB
    J --> DB
    W --> H
~~~

| Thành phần | Vai trò | Khi chọn |
|---|---|---|
| **Cloud Scheduler** | Gửi sự kiện/yêu cầu theo giờ, ngày hoặc lịch cron | Công việc lặp lại có thời điểm xác định |
| **Cloud Run service** | Nhận HTTPS request, xử lý tác vụ trong giới hạn request | API Java xử lý nhanh hoặc kích hoạt durable work |
| **Cloud Run Job** | Chạy container đến khi hoàn thành; không cần HTTP listener của container | Batch Java, ETL, xử lý theo lô hoặc thời gian dài |
| **Pub/Sub** | Đệm và phân phối messages tới consumers | Tách lịch khỏi tốc độ xử lý, chịu tải bất đồng bộ |
| **Workflows** | Gọi tuần tự/song song các dịch vụ, retry, điều kiện và xử lý lỗi | Quy trình tích hợp nhiều bước/dịch vụ |
| **Cloud Tasks** | Hàng đợi tác vụ HTTP với thời gian thực thi có thể đặt cho từng task | Một việc xảy ra **một lần trong tương lai**, không phải cron định kỳ |

**Không mặc định Scheduler bảo đảm công việc đã hoàn tất.** Với Pub/Sub target, Scheduler thành công khi **publish tới topic**, không đợi Java consumer commit database. Với Cloud Run Jobs API, phản hồi HTTP thành công thường chỉ nghĩa **execution đã được yêu cầu/khởi tạo**, không chứng minh batch chạy xong.

## 3. Cấu hình lịch cron và múi giờ

### 3.1. Unix-cron có năm trường

~~~text
┌──────── phút        (0–59)
│ ┌────── giờ         (0–23)
│ │ ┌──── ngày tháng  (1–31)
│ │ │ ┌── tháng       (1–12)
│ │ │ │ ┌ ngày tuần  (0–7, SUN=0/7)
│ │ │ │ │
0  18  *  *  *
~~~

Ví dụ:

| Biểu thức | Nghĩa |
|---|---|
| `*/5 * * * *` | Mỗi 5 phút |
| `0 * * * *` | Đầu mỗi giờ |
| `0 18 * * *` | Mỗi ngày lúc 18:00 theo timezone đã chọn |
| `30 8 * * 1-5` | Thứ Hai–thứ Sáu lúc 08:30 |
| `0 2 1 * *` | Ngày 1 hằng tháng lúc 02:00 |
| `0 6 * * 0` | Chủ Nhật lúc 06:00 |

**Đọc theo múi giờ của job**, không theo múi giờ laptop hoặc vị trí cluster. `0 18 * * *` với `Asia/Ho_Chi_Minh` chạy lúc 18:00 giờ Việt Nam; với `Etc/UTC` chạy lúc 18:00 UTC. Không suy lịch từ `--location`: **region lưu Scheduler job không quyết định timezone**.

### 3.2. DST và tính chính xác của lịch

- Mặc định Cloud Scheduler dùng **UTC** khi không chỉ định timezone.
- Múi giờ hỗ trợ tên từ **IANA tz database**, ví dụ `Asia/Ho_Chi_Minh`, `America/Los_Angeles` và `Etc/UTC`.
- Ở những vùng có **daylight saving time**, giờ địa phương có thể **không tồn tại** hoặc **lặp hai lần**, khiến lịch theo wall clock không đều.
- Nếu cần cadence ổn định hoặc xử lý tài chính, **ưu tiên UTC**; nếu nghiệp vụ phụ thuộc giờ địa phương, lưu rõ timezone và có test cho DST.

Cloud Scheduler cũng hỗ trợ biểu thức **groc** dễ đọc, ví dụ `every 5 minutes` hoặc `first sunday of month 04:00`. Tuy nhiên, **`X-CloudScheduler-ScheduleTime` không được bảo đảm gửi cho groc**, nên nếu dự định dùng chính header này để chống chạy trùng, hãy **chọn unix-cron**.

### 3.3. Lịch định kỳ không giống một lần chạy

| Yêu cầu | Giải pháp phù hợp |
|---|---|
| Mỗi đêm 18:00 tổng hợp báo cáo | Scheduler cron |
| Mỗi 15 phút gửi tín hiệu làm mới cache | Scheduler → Pub/Sub |
| Đúng một lần vào 14:30 ngày mai | Cloud Tasks với scheduleTime hoặc giải pháp one-shot phù hợp |
| Người dùng tạo hàng triệu thời điểm hẹn riêng | Cloud Tasks/queue, không tạo một cron job cho từng event |
| Sau giờ đóng sổ cần chạy 4 API nối tiếp | Scheduler → Workflows |
| Batch Java 2 giờ | Scheduler → Cloud Run Job/Workflows, **không** giữ HTTP request chờ 2 giờ |

**Góc vận hành:** khi Cloud Scheduler API bị tắt rồi bật lại, các kỳ lỡ trong thời gian tắt có thể được kích hoạt **ngay khi bật**, không chờ lịch tương lai. Vì thế không dùng tắt API như cơ chế “pause job” và không giả định không có catch-up.

## 4. Chọn target: HTTP, Pub/Sub hay App Engine?

| Target | Scheduler gửi gì? | Khi nào dùng? | Rủi ro cần xử lý |
|---|---|---|---|
| **HTTP/S** | HTTP method, headers, body, OIDC/OAuth token nếu cấu hình | Cloud Run Java service, Workflows/Cloud Run Jobs APIs | Auth, timeout, status code và idempotency |
| **Pub/Sub** | Message vào topic | Xử lý bất đồng bộ, có nhiều subscribers | Scheduler thành công **không** chứng minh consumer xong; cần Pub/Sub retry/DLQ |
| **App Engine HTTP** | HTTP tới App Engine application cùng project | Hệ thống đang dùng App Engine | Giới hạn region, routing, scaling và quyền target |

**HTTP target** là ví dụ chính của bài. Với Cloud Run service, endpoint cần có **địa chỉ HTTPS có thể được Scheduler kết nối**; vẫn có thể **private theo IAM**. Đừng đánh đồng “URL truy cập được” với “cho phép caller không xác thực”. Với các cấu hình ingress chỉ internal, cần kiểm tra hướng dẫn Cloud Run/Cloud Scheduler và vị trí dự án/perimeter thay vì suy mọi URL HTTPS đều kết nối được.

**App Engine target** đòi hỏi app ở project và job theo location của App Engine app. Nếu không sử dụng App Engine, **không cần tạo App Engine application** chỉ để dùng Cloud Scheduler.

## 5. Xác thực và IAM cho HTTP target

### 5.1. Ba danh tính riêng

~~~mermaid
flowchart LR
    Deployer["Developer/CI<br/>tạo Scheduler job"]
    JobSA["scheduler-caller SA<br/>OIDC hoặc OAuth"]
    Agent["Cloud Scheduler service agent<br/>do Google quản lý"]
    Scheduler["Cloud Scheduler job"]
    Run["Cloud Run Java<br/>private target"]
    Runtime["Cloud Run runtime SA"]
    DB["Cloud SQL / APIs"]
    Deployer -->|"create job + actAs"| Scheduler
    Agent -. "Mint token thay JobSA" .-> Scheduler
    Scheduler -->|"authenticated request as JobSA"| Run
    JobSA -. "run.invoker trên target" .-> Run
    Run -->|"ADC / runtime SA"| DB
    Runtime -. "DB/API permissions" .-> DB
~~~

| Principal | Quyền / vai trò | Lý do |
|---|---|---|
| **Người tạo/quản trị Scheduler job** | `roles/cloudscheduler.admin` hoặc custom role; `iam.serviceAccounts.actAs` trên SA gắn job | Được tạo/sửa job và chọn caller identity |
| **Job caller service account** | `roles/run.invoker` trên Cloud Run service đích | Scheduler gọi private Cloud Run dưới identity này |
| **Cloud Scheduler service agent** | `roles/cloudscheduler.serviceAgent` trên project, do Google quản lý | Phát hành auth tokens/điều phối yêu cầu |
| **Cloud Run runtime SA** | Quyền Cloud SQL, Storage, Pub/Sub... **theo nghiệp vụ** | Mã Java dùng ADC khi gọi API |
| **Job operator** | `roles/cloudscheduler.jobRunner` nếu chỉ cần chạy job có sẵn | Không cần toàn quyền quản lý Scheduler |

**Quan trọng:** không dùng email `service-PROJECT_NUMBER@gcp-sa-cloudscheduler.iam.gserviceaccount.com` làm **job caller SA**; đó là service agent của Google. Đối với HTTP target có auth, job caller SA phải thuộc **cùng project với Scheduler job**. Không cấp `roles/cloudscheduler.serviceAgent` cho user-managed SA.

Cloud Scheduler IAM cho các jobs chủ yếu ở **project scope**; không mặc định có thể cấp permission chỉ trên một Scheduler job. Nếu cần tách người quản trị job thuộc các nhóm, cân nhắc **tách project**; còn quyền gọi target nên giới hạn theo **service đích**.

### 5.2. OIDC hay OAuth?

| Đích đến | Token phù hợp | Ví dụ |
|---|---|---|
| **Private Cloud Run service/function** | **OIDC ID token**, audience đúng service | `https://...run.app` |
| **Google API endpoint** `*.googleapis.com` | **OAuth 2.0 access token** | `https://run.googleapis.com/v2/...:run` |
| **Workflows Executions REST API** | **OAuth access token** | `https://workflowexecutions.googleapis.com/v1/...` |
| **API bên thứ ba** | Tùy cơ chế auth của provider; nếu dùng OIDC, receiver phải xác minh token | HTTPS external endpoint |

Với Cloud Run HTTP endpoint ở `https://HOST/internal/close-day`, **OIDC audience nên là base service URL `https://HOST`** theo khả năng chấp nhận audience của Cloud Run, không chứa query parameters. Nếu `--oidc-token-audience` không được chỉ định, Scheduler dùng **toàn bộ target URI** làm audience; điều này có thể gây 401/403 nếu service kiểm tra audience khác.

**Không commit service account JSON key hay access token vào scheduler job body/header.** Scheduler tự phát hành token ngắn hạn thay job caller SA. Sau khi request vào Cloud Run, Java runtime dùng **runtime SA khác**, không tự kế thừa mọi quyền của caller SA.

### 5.3. Phân biệt ba lớp kiểm soát

- **IAM Invoker:** job caller có quyền gọi Cloud Run service không?
- **Ingress / network:** yêu cầu có đến được Cloud Run ingress theo policy đã chọn không?
- **Business authorization:** Java có chấp nhận hành động này ở kỳ lịch và phạm vi dữ liệu tương ứng không?

Một header `X-CloudScheduler-*` **không phải chứng cứ xác thực**, vì caller khác có thể tự gửi header giống hệt. Phải bảo vệ endpoint bằng OIDC/IAM trước khi sử dụng headers để lập idempotency key.

## 6. Thực hành A — Scheduler gọi private Java Cloud Run service

**Mục tiêu:** vào 18:00 mỗi ngày theo giờ Việt Nam, Scheduler gửi một HTTP POST tới `/internal/close-day` của Java Spring Boot service. Mẫu Java chỉ log kỳ lịch và trả HTTP 204; phần xử lý bền vững trình bày ở mục 7.

### 6.1. Chuẩn bị

| Thuộc tính | Giá trị minh họa |
|---|---|
| Project | `PROJECT_ID` |
| Scheduler location | `asia-southeast1` |
| Cloud Run service | `daily-close-api` tại `asia-southeast1` |
| Cloud Run HTTPS URL | `https://SERVICE_HOST` (lấy từ `gcloud` thật) |
| Job ID | `daily-close-schedule` |
| Job caller SA | `scheduler-caller@PROJECT_ID.iam.gserviceaccount.com` |
| Cron | `0 18 * * *` |
| Timezone | `Asia/Ho_Chi_Minh` |

Yêu cầu: project có billing, `cloudscheduler.googleapis.com` và Cloud Run APIs được bật; Java service đã được deploy private và sẵn sàng; quyền tạo SA/job/IAM được phê duyệt. Nếu chưa có service, hãy deploy Java Spring Boot endpoint theo quy trình của nhóm **trước khi** tạo job.

Lệnh đọc không thay đổi tài nguyên:

~~~bash
gcloud auth list
gcloud config get-value project

gcloud run services describe daily-close-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --format="value(status.url)"

gcloud scheduler jobs list \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

### 6.2. Java Spring Boot handler tối giản

Dự án Java 17 với Spring Boot Web starter có thể có controller:

~~~java
package com.example.scheduler;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public final class DailyCloseController {
    private static final Logger log =
        LoggerFactory.getLogger(DailyCloseController.class);

    @PostMapping("/internal/close-day")
    public ResponseEntity<Void> closeDay(
        @RequestHeader(value = "X-CloudScheduler-JobName",
                       required = false) String jobName,
        @RequestHeader(value = "X-CloudScheduler-ScheduleTime",
                       required = false) String scheduleTime
    ) {
        // Chỉ demo: ghi metadata, chưa thực thi nghiệp vụ.
        log.info("Scheduled call: job={} time={}", jobName, scheduleTime);
        return ResponseEntity.noContent().build();
    }
}
~~~

Controller cần đặt trong package được `@SpringBootApplication` quét; ứng dụng Spring Boot phải chạy trên port Cloud Run cấp qua biến `PORT` theo cấu hình runtime. Với bài lab, handler không ghi dữ liệu nên tránh gây side effects khi chạy thử. **Trả 204 trong demo chỉ xác nhận request đã tới handler**, không chứng minh đã đóng sổ kế toán.

### 6.3. Tạo user-managed caller SA và cấp Invoker

**Các lệnh sau thay đổi tài nguyên thật**:

~~~bash
gcloud iam service-accounts create scheduler-caller \
  --project=PROJECT_ID \
  --display-name="Scheduler to private Cloud Run caller"

gcloud run services add-iam-policy-binding daily-close-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --member="serviceAccount:scheduler-caller@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
~~~

Người tạo job phải có quyền `iam.serviceAccounts.actAs` trên SA này. Nếu thiếu, yêu cầu admin cấp **`roles/iam.serviceAccountUser` cho deployer trên đúng SA**. Không cấp `Owner` toàn project để sửa lỗi nhỏ. Kiểm tra service IAM:

~~~bash
gcloud run services get-iam-policy daily-close-api \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

### 6.4. Tạo HTTP job có OIDC và retry giới hạn

Thay `SERVICE_HOST` bằng hostname thực của Cloud Run service (không bao gồm `https://`). Mọi request trong ví dụ chỉ chứa metadata demo không nhạy cảm.

~~~bash
gcloud scheduler jobs create http daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --schedule="0 18 * * *" \
  --time-zone="Asia/Ho_Chi_Minh" \
  --uri="https://SERVICE_HOST/internal/close-day" \
  --http-method=POST \
  --headers="Content-Type=application/json" \
  --message-body='{"reason":"scheduled-day-close"}' \
  --oidc-service-account-email="scheduler-caller@PROJECT_ID.iam.gserviceaccount.com" \
  --oidc-token-audience="https://SERVICE_HOST" \
  --attempt-deadline=120s \
  --max-retry-attempts=3 \
  --min-backoff=10s \
  --max-backoff=60s
~~~

Giải thích:

- `--schedule` và `--time-zone` quyết định kỳ lịch, không phải Cloud Run region.
- `--oidc-service-account-email` là **job caller**, có Invoker trên đúng service.
- `--oidc-token-audience` phải đúng audience mà Cloud Run kiểm tra; không dùng URL có query parameters.
- `--attempt-deadline=120s` giới hạn thời gian Scheduler chờ **một HTTP attempt**.
- `--max-retry-attempts=3` cho phép retry theo chính sách khi attempt thất bại; **không** bảo đảm mỗi kỳ chỉ chạy đúng một lần.
- `--message-body` chỉ gửi cho POST/PUT; API không tự hiểu body là secret hoặc mệnh lệnh đáng tin.

### 6.5. Đọc cấu hình, chạy thử và xem log

~~~bash
gcloud scheduler jobs describe daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

# Lệnh này KÍCH HOẠT request thật ngay lập tức.
gcloud scheduler jobs run daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud run services logs read daily-close-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --limit=50
~~~

Quan sát Cloud Scheduler job status/logs, Cloud Run request logs và một dòng `Scheduled call`. Khi test trên handler có tác động nghiệp vụ, phải dùng **sandbox và dedup**; `jobs run` không phải dry run.

**Lưu ý quan trọng khi chạy thủ công:** `X-CloudScheduler-ScheduleTime` có thể bằng thời gian của kỳ lịch sắp tới hoặc **không có**. Nếu dùng header này làm dedup key, manual run có thể làm kỳ lịch kế tiếp bị xem như đã xử lý. Vì vậy đừng dùng `jobs run` để kiểm tra đóng sổ thật mà không có chế độ test riêng.

## 7. At-least-once và chống chạy trùng trong Java

### 7.1. Tại sao một kỳ lịch có thể bị gọi hai lần?

~~~mermaid
sequenceDiagram
    participant S as Cloud Scheduler
    participant R as Cloud Run Java
    participant DB as Cloud SQL
    S->>R: POST run=2026-11-19T11:00Z
    R->>DB: COMMIT đóng sổ
    Note over S,R: Response 204 bị mất do network
    S->>R: Retry cùng scheduled time
    R->>DB: Check unique run key → đã xử lý
    R-->>S: 204, không thực hiện lần nữa
~~~

Cloud Scheduler có **at-least-once delivery**: mất HTTP response hoặc timeout có thể dẫn đến gửi lại cùng kỳ, dù backend đã commit. Đặt retry count = 0 **không đủ** để cam kết tuyệt đối không bao giờ có duplicate do lỗi vận chuyển.

### 7.2. Header hỗ trợ dedup

Cloud Scheduler gửi trên HTTP/App Engine targets có unix-cron:

- `X-CloudScheduler-JobName`: định danh job.
- `X-CloudScheduler-ScheduleTime`: thời điểm kỳ lịch theo RFC 3339; **giữ nguyên qua các retry của cùng kỳ**.

Tạo khóa `project + region + jobName + scheduleTime`, vì jobName riêng lẻ có thể trùng giữa project/region. **Đừng tin header là authentication**; đòi OIDC/IAM ở Cloud Run. Với groc không đảm bảo `ScheduleTime`; với manual `jobs run` phải có nhánh kiểm thử riêng.

### 7.3. Mẫu transaction/unique constraint cho Cloud SQL

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE scheduler_runs (
    job_name TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (job_name, scheduled_at)
);

CREATE TABLE daily_close_results (
    business_date DATE PRIMARY KEY,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong **một transaction**, Java chạy:

~~~sql
BEGIN;

-- Marker dùng để bảo đảm một kỳ lịch chỉ được xử lý một lần.
INSERT INTO scheduler_runs (job_name, scheduled_at)
VALUES ('daily-close-schedule', '2026-11-19T11:00:00Z')
ON CONFLICT DO NOTHING;

-- Ứng dụng phải kiểm tra affected rows của INSERT:
-- = 0 → đã hoàn thành theo transaction trước: COMMIT và trả 204.
-- = 1 → thực hiện nghiệp vụ dưới đây, trong cùng transaction.
INSERT INTO daily_close_results (business_date)
VALUES (DATE '2026-11-19')
ON CONFLICT (business_date)
DO UPDATE SET completed_at = now();

COMMIT;
~~~

**Cảnh báo:** đoạn SQL trên là **mẫu luồng xử lý**, không phải script tự rẽ nhánh. **Java phải bỏ qua UPDATE nếu INSERT marker không thêm dòng mới**, và phải rollback cả marker lẫn nghiệp vụ nếu xử lý thất bại. Nếu tác vụ gồm gọi external payment/email/API ngoài transaction, cần **idempotency key đầu cuối, outbox hoặc workflow**; một unique marker trong Cloud SQL không thể tự rollback HTTP call đã hoàn tất.

### 7.4. Thiết kế khóa và lock theo phạm vi nghiệp vụ

| Yêu cầu | Key / guardrail |
|---|---|
| Không đóng sổ hai lần cùng kỳ | `jobName + scheduledTime` |
| Không đóng sổ hai lần cho cùng ngày kinh doanh | Unique `businessDate` độc lập kỳ lịch |
| Nhiều project/regions cùng gọi một service | Gắn `project + region` vào key |
| Chỉ một worker xử lý khi job chạy lâu | Durable claim/lease với TTL và fencing token |
| Ghi vào Pub/Sub rồi cập nhật DB | Transactional outbox; không giả định cross-service atomicity |
| Manual replay/backfill | Run ID riêng, phân biệt và được phê duyệt |

**Không dùng `synchronized` trong Java hoặc in-memory set làm lock phân tán:** Cloud Run có thể scale nhiều instances và restart. Với workflow nhiều bước, dùng transaction/conditional write tại datastore phù hợp, có trạng thái `IN_PROGRESS`/`COMPLETED`, lease expiration và cách xử lý job bị chết.

## 8. Retry, attempt deadline và lịch chồng lấp

### 8.1. Khi nào Scheduler coi attempt thành công?

| Target | Thành công nhìn từ Scheduler |
|---|---|
| **HTTP** | Target trả HTTP **2xx** trước `attemptDeadline` |
| **Pub/Sub** | Publish message vào topic được chấp nhận |
| **App Engine** | Target HTTP đáp ứng theo hành vi thành công và timeout phù hợp |

**HTTP 202 Accepted** vẫn là 2xx. Nếu Java API trả 202 nhưng chỉ lưu task trong RAM, Scheduler có thể coi hoàn tất trong khi task mất khi instance crash. Với xử lý bất đồng bộ, chỉ trả 2xx sau khi **ghi durable queue/store**, hoặc dùng Cloud Run Jobs/Workflows API đúng semantics và theo dõi execution riêng.

### 8.2. Các tham số retry

| Thuộc tính | Mục đích | Mặc định / giới hạn cần nhớ |
|---|---|---|
| `attemptDeadline` (HTTP) | Thời gian chờ một HTTP attempt | **3 phút mặc định**, cấu hình **15 giây–30 phút** |
| `retryCount` / `--max-retry-attempts` | Số lần retry theo giới hạn | **0 mặc định**, tối đa **5** ở cấu hình retry |
| `maxRetryDuration` | Cửa sổ retry từ attempt đầu | **0 mặc định**, cần hiểu tương tác với retryCount |
| `minBackoffDuration` | Khoảng đợi retry ban đầu | **5 giây mặc định** |
| `maxBackoffDuration` | Trần khoảng cách retry | **1 giờ mặc định** |
| `maxDoublings` | Số nhịp exponential doubling trước giai đoạn linear | **5 mặc định** |

**Mặc định retryCount=0 và maxRetryDuration=0** nghĩa là không retry theo policy khi thất bại; kỳ theo lịch tiếp theo vẫn được kích hoạt. Đối với hai giới hạn retryCount và maxRetryDuration, hành vi không thể suy đơn giản bằng phép cộng; xem tài liệu `RetryConfig` và test cấu hình thực tế.

### 8.3. Một kỳ chạy quá lâu sẽ ảnh hưởng kỳ sau

Cloud Scheduler thường tránh giữ **hai lần chạy outstanding của cùng job đồng thời**. Nếu attempt trước còn chờ phản hồi, kỳ tiếp có thể **bị trì hoãn hoặc bỏ qua**, nhất là khi retry kéo dài. Tuy nhiên một request đã timeout ở Scheduler có thể vẫn đang **tiếp tục xử lý phía backend**, và duplicate requests vẫn có thể xảy ra trong tình huống hiếm.

Ví dụ job chạy mỗi 5 phút, HTTP backend mất 12 phút:

- Với attempt deadline 3 phút, Scheduler có thể coi timeout và retry khi backend còn chạy.
- Nếu retry đè lên thời gian của kỳ mới, lịch kế tiếp có thể không bắt đầu như dự kiến.
- Nếu API Java không có idempotency/lease, nhiều instances có thể cùng ghi business data.

**Giải pháp:** trigger **durable asynchronous work** rồi trả response nhanh, hoặc chạy Cloud Run Job có execution tracking; thêm distributed claim/lock và giới hạn xử lý theo SLO. Không biến Scheduler thành worker chạy mã dài hàng giờ qua một HTTP request.

## 9. Thực hành B — Scheduler gửi Pub/Sub message

Chọn Pub/Sub nếu muốn **tách thời điểm kích hoạt khỏi tốc độ xử lý** của Java worker trên GKE/VM/Cloud Run.

~~~mermaid
flowchart LR
    Sch["Scheduler mỗi 15 phút"]
    Topic["Pub/Sub topic<br/>refresh-cache"]
    Sub["Subscription<br/>refresh-cache-sub"]
    Java["Java worker"]
    DB["Cloud SQL / cache"]
    Sch -->|"Publish thành công"| Topic
    Topic --> Sub
    Sub -->|"At-least-once delivery"| Java
    Java --> DB
~~~

Tạo tài nguyên lab khi có quyền:

~~~bash
gcloud pubsub topics create refresh-cache-tick \
  --project=PROJECT_ID

gcloud pubsub subscriptions create refresh-cache-sub \
  --project=PROJECT_ID \
  --topic=refresh-cache-tick

gcloud scheduler jobs create pubsub refresh-cache-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --schedule="*/15 * * * *" \
  --time-zone="Etc/UTC" \
  --topic=refresh-cache-tick \
  --message-body='{"task":"refresh-cache"}'
~~~

**Phân biệt hai lớp xác nhận:**

1. Scheduler publish message đến Pub/Sub → job attempt **thành công**.
2. Subscriber Java nhận và xử lý message → **acknowledgment riêng** với retry/DLQ của Pub/Sub.

Nếu subscriber lỗi, Scheduler vẫn có thể báo success, còn backlog của Pub/Sub tăng. Vì vậy cần **hai bộ metrics** (Scheduler và Pub/Sub), cùng idempotency theo kỳ lịch hoặc business event. Scheduler **service agent** có quyền publish theo cơ chế dịch vụ; không tự cấp role Admin cho worker chỉ để Scheduler hoạt động.

## 10. Thực hành C — Lên lịch Cloud Run Job hoặc Workflows

### 10.1. Cloud Run Job cho batch Java

Java batch xử lý hàng triệu bản ghi thường không cần đứng chờ HTTP request. Triển khai container dưới dạng **Cloud Run Job** với timeout/retries của Cloud Run Job riêng. Cloud Scheduler gửi HTTP POST tới Cloud Run Admin API:

~~~text
https://run.googleapis.com/v2/projects/PROJECT_ID/locations/asia-southeast1/jobs/nightly-batch:run
~~~

Ví dụ (Cloud Run Job `nightly-batch` đã tồn tại):

~~~bash
gcloud scheduler jobs create http nightly-batch-trigger \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --schedule="0 1 * * *" \
  --time-zone="Etc/UTC" \
  --uri="https://run.googleapis.com/v2/projects/PROJECT_ID/locations/asia-southeast1/jobs/nightly-batch:run" \
  --http-method=POST \
  --oauth-service-account-email="scheduler-caller@PROJECT_ID.iam.gserviceaccount.com"
~~~

**Khác với mục 6:** target là **`run.googleapis.com`**, nên dùng **OAuth access token**, không dùng OIDC ID token. Job caller SA cần quyền chạy Cloud Run Job, ví dụ `roles/run.invoker` trên đúng job theo hướng dẫn Cloud Run. Runtime SA của batch container lại cần quyền dữ liệu riêng.

Scheduler nhận HTTP thành công nghĩa là **execution đã được yêu cầu**; phải kiểm tra **Cloud Run Job execution status/logs** để biết batch thành công hay thất bại. Nếu Scheduler retry sau lỗi mạng dù execution đã được tạo, có thể tạo **nhiều executions**. Để chống trùng, dùng proxy/idempotency token hoặc bảo vệ trong nghiệp vụ downstream.

### 10.2. Workflows cho tích hợp nhiều bước

Ví dụ chuỗi: tổng hợp đơn hàng → cập nhật Cloud SQL → gửi Pub/Sub → ghi audit. Với Workflows:

~~~mermaid
flowchart TD
    S["Cloud Scheduler"] -->|"OAuth POST executions"| W["Workflows execution"]
    W --> A["Gọi Java Orders API"]
    A --> D["Kiểm tra dữ liệu"]
    D --> P["Publish event"]
    P --> L["Ghi audit + kết thúc"]
    W -. "Retry + error handling" .-> A
~~~

Scheduler có thể gọi **Workflows Executions API** qua `https://workflowexecutions.googleapis.com/v1/projects/.../executions` với OAuth và service account có `roles/workflows.invoker` theo scope phù hợp. Workflows quản lý thứ tự, điều kiện và retry của các bước; Scheduler vẫn chỉ làm **trigger**.

Một HTTP response thành công từ Executions API **không tự chứng minh các bước Workflows đã chạy xong**. Hãy theo dõi execution state và đặt idempotency token xuyên các bước có side effect.

### 10.3. Mẫu chọn kiến trúc

| Đặc điểm công việc | Phương án |
|---|---|
| Handler Java 2 giây, một HTTP call | Scheduler → private Cloud Run service |
| Cần worker xử lý hàng đợi, có DLQ | Scheduler → Pub/Sub → subscriber |
| Java CLI chạy 45 phút, có exit code | Scheduler → Cloud Run Job |
| 5 API có retry/nhánh lỗi/compensation | Scheduler → Workflows |
| Hẹn xử lý một hóa đơn vào đúng ngày giờ riêng | Cloud Tasks hoặc lịch nghiệp vụ chuyên biệt |

## 11. Vận hành: pause, resume, update, xóa

### 11.1. Bộ lệnh quản trị

~~~bash
# Chỉ đọc trạng thái:
gcloud scheduler jobs list \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud scheduler jobs describe daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

# Các lệnh sau THAY ĐỔI trạng thái job:
gcloud scheduler jobs pause daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud scheduler jobs resume daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud scheduler jobs update http daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --schedule="30 18 * * *" \
  --time-zone="Asia/Ho_Chi_Minh"
~~~

**Pause** là cách dừng trigger theo quản trị job, **không tự hủy HTTP request hoặc Cloud Run execution đã bắt đầu**. **Resume** cần kiểm tra backlog/điều kiện nghiệp vụ; không tự cho rằng mọi kỳ đã lỡ sẽ được xử lý giống nhau. Cập nhật schedule phải được kiểm thử vì có thể đổi mốc đóng sổ và timezone semantics.

### 11.2. Xóa tài nguyên lab

Sau khi xác minh job và service account không được consumer khác dùng:

~~~bash
gcloud scheduler jobs delete daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud scheduler jobs delete refresh-cache-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud scheduler jobs delete nightly-batch-trigger \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

Đây là **ví dụ cleanup theo những bài lab đã tạo**, không chạy hàng loạt nếu tài nguyên chưa tồn tại/được chia sẻ. Xóa Scheduler job **không xóa** Cloud Run Job executions, Pub/Sub messages hoặc dữ liệu Cloud SQL mà target đã tạo.

## 12. Quan sát và xử lý lỗi

### 12.1. Xem được gì?

| Thành phần | Tín hiệu | Cần phân biệt |
|---|---|---|
| **Cloud Scheduler** | Job status, last attempt, attempt logs, scheduled time, retry | Request được gửi/thành công ở lớp trigger |
| **Cloud Run service** | HTTP 2xx/4xx/5xx, latency, container logs, instances | Handler có xử lý và commit thực sự không |
| **Cloud Run Job** | Executions, task failures, exit codes, duration | Batch đã chạy xong hay chỉ được yêu cầu |
| **Pub/Sub** | Backlog age, delivery failures, DLQ | Subscriber có tiêu thụ xong không |
| **Workflows** | Execution state, step failures, retries | Luồng tích hợp hoàn tất tới bước nào |
| **Cloud SQL** | Unique key violations, transactions, locks | Dữ liệu có chính xác sau retry không |
| **Billing** | Scheduler jobs, Cloud Run, Pub/Sub, Workflows, logs/egress | Retry/tần suất có làm chi phí tăng không |

Cloud Scheduler logs có các bản ghi `AttemptStarted` và `AttemptFinished`. Khi job không thấy chạy kỳ kế tiếp, tìm attempt chưa kết thúc hoặc quá hạn, trước khi tạo job thứ hai. Các logs/metrics thực tế cần cấp Logging Viewer/Monitoring Viewer phù hợp.

### 12.2. Bảng chẩn đoán nhanh

| Hiện tượng | Nguyên nhân thường gặp | Hướng giải quyết |
|---|---|---|
| HTTP 401/403 gọi private Cloud Run | Job caller SA thiếu `roles/run.invoker` hoặc OIDC audience sai | Kiểm tra SA gắn job, IAM target, audience |
| 403 dù job caller có Invoker | Cloud Scheduler service agent mất `roles/cloudscheduler.serviceAgent` | Kiểm tra principal Google-managed và role; không gán nhầm user SA |
| 401 gọi `run.googleapis.com` hoặc Workflows API | Dùng OIDC thay vì OAuth, hoặc thiếu API role | Đổi OAuth target, kiểm tra quyền chạy job/workflow |
| HTTP 404 | Sai URL/path/region hoặc target đã đổi | Describe Cloud Run service/Cloud Run Job và Scheduler URI |
| HTTP 429/503 | Target quá tải, DB connection pool cạn | Giảm tần suất/retry, scaling, backpressure |
| `DEADLINE_EXCEEDED` | Backend chậm hơn attempt deadline | Điều chỉnh timeout hợp lý, chuyển sang async Job/Workflows |
| Scheduler success nhưng DB chưa cập nhật | HTTP trả 2xx trước durable commit, hoặc Pub/Sub consumer lỗi | Xem downstream logs/backlog và giao dịch |
| Cùng kỳ chạy hai lần | Retry/transport duplicate hoặc manual run | Durable idempotency theo jobName/scheduleTime |
| Job không chạy lúc mong muốn | Cron/timezone/DST sai, pause hoặc API bị tắt | Describe job, timezone, trạng thái, logs |
| Kỳ sau không được kích hoạt | Attempt trước đang chờ hoặc retry trùng lịch | Xem `AttemptStarted`/`AttemptFinished` và retry policy |
| Lịch test thủ công làm ngày sau bị skip | Dùng scheduleTime của kỳ tiếp theo làm dedup key | Thiết kế manual/backfill run ID riêng |
| Chi phí cao | Quá nhiều jobs/tần suất, downstream compute/logging | Billing, cost per successful business run |

### 12.3. Quy trình xử lý sự cố

1. Xác định **project, region, job ID, schedule/timezone** và target.
2. Kiểm tra `gcloud scheduler jobs describe`: paused/enabled, URI, SA, retry, attempt deadline.
3. Soi `AttemptStarted`/`AttemptFinished` và HTTP status; phân biệt lỗi trigger với lỗi downstream.
4. Nếu 401/403: kiểm tra **OIDC vs OAuth**, audience, job caller SA, target IAM và Scheduler service agent.
5. Nếu timeout: xem Cloud Run request timeout, Java logs/GC, Cloud SQL latency và mục tiêu xử lý.
6. Nếu success nhưng nghiệp vụ thất bại: theo dõi **Cloud Run Job execution, Workflows execution hoặc Pub/Sub consumer**.
7. Nếu duplicate: dùng key bền vững, tránh replay trước khi biết side effects đã xảy ra.
8. Sửa trong sandbox, thử failure/retry/manual, rồi theo dõi SLO và chi phí.

**Không chữa lỗi 403 bằng cách mở Cloud Run public hoặc gán Owner**, và không khôi phục một kỳ lịch chưa chắc thiếu dữ liệu bằng manual replay không idempotent.

## 13. SLO, chi phí và hạn mức

### 13.1. SLO không nên chỉ dựa trên Scheduler job success

Ví dụ yêu cầu: **báo cáo bán hàng của hôm trước có trước 07:00**. SLO đúng nên là:

~~~text
SLO hoàn tất nghiệp vụ =
  thời điểm dữ liệu đã xử lý + báo cáo sẵn sàng
  <= 07:00 theo múi giờ kinh doanh
~~~

Scheduler job HTTP trả 202 lúc 06:00 có thể đạt SLO trigger nhưng **không chứng minh** báo cáo đã hoàn thành. Cần metric end-to-end từ Java/Workflows/Job execution và dữ liệu kết quả.

### 13.2. Những nguồn chi phí

- Cloud Scheduler job count/tần suất và chính sách giá hiện hành.
- Cloud Run compute/requests khi target được gọi, Cloud Run Jobs executions.
- Pub/Sub messages, Workflows steps, Cloud Tasks nếu kết hợp.
- Cloud SQL query/storage, mạng, Cloud Logging và Monitoring.
- Lưu lượng retry và xử lý duplicate, thời gian vận hành khi lỗi.

Dùng **Billing Reports**, **Budgets and alerts** và pricing pages hiện hành; tránh đoán đơn giá USD khi chưa biết location, SKU và pattern chạy.

### 13.3. Quota và giới hạn

Cloud Scheduler có quota theo **project/region**, số jobs, API read/write và **kích thước request payload**. Nếu cron chạy mỗi phút trên hàng nghìn jobs, trước tiên cân nhắc gom trigger, phân bổ project hoặc queue processing phù hợp. Với HTTP target, **attempt deadline tối đa 30 phút**, không phù hợp dùng làm batch worker dài.

Tài liệu giới hạn dịch vụ có thể thay đổi: kiểm tra **Cloud Scheduler quotas and limits** trước khi đưa giá trị vào thiết kế capacity hoặc SLA.

## 14. Case study: đối soát đơn hàng mỗi ngày

### 14.1. Bối cảnh

Một công ty bán lẻ có **Orders API Java** trên Cloud Run và Cloud SQL PostgreSQL. Cuối mỗi ngày theo `Asia/Ho_Chi_Minh`, hệ thống cần:

1. Chốt danh sách đơn.
2. Tính tổng doanh thu.
3. Gửi sự kiện `DAILY_CLOSED` cho Billing và Analytics.
4. Có báo cáo hoàn chỉnh trước 07:00 ngày hôm sau.

Batch có thể mất **45 phút**, thỉnh thoảng Cloud SQL bị chậm. Có yêu cầu **không chốt/gửi thanh toán hai lần**.

### 14.2. Kiến trúc đề xuất

~~~mermaid
flowchart LR
    Sch["Scheduler 18:00 Asia/Ho_Chi_Minh"]
    WF["Workflows<br/>execution + retries"]
    Batch["Cloud Run Job<br/>Java close-day"]
    DB["Cloud SQL<br/>transaction + idempotency"]
    Pub["Pub/Sub DAILY_CLOSED"]
    Mon["Monitoring & alert"]
    Sch -->|"OAuth start"| WF
    WF --> Batch
    Batch --> DB
    WF --> Pub
    WF -. "execution status" .-> Mon
    Batch -. "result metrics" .-> Mon
~~~

**Tại sao không Scheduler → Java HTTP chờ 45 phút?** Cloud Scheduler HTTP attempt deadline tối đa 30 phút. Nếu giữ HTTP request qua giới hạn, Scheduler có thể timeout/retry trong khi Java vẫn xử lý, dẫn tới side effects trùng. **Cloud Run Job** thích hợp hơn cho batch lâu; **Workflows** điều phối các bước và kiểm tra trạng thái. Scheduler chỉ cần phát một trigger đúng kỳ.

**Thiết kế tính đúng đắn:**

- Key `businessDate` để đóng sổ đúng một lần; `scheduleTime` để nhận diện kỳ.
- Durable claim/transaction có trạng thái và fencing nếu cần, không dùng in-memory lock.
- Outbox cho sự kiện `DAILY_CLOSED` để tránh DB commit xong nhưng publish lỗi.
- Workflows/Job retries đều idempotent; timeouts và alerts theo SLO.
- Nếu Scheduler gọi Workflows API trực tiếp và request bị retry sau phản hồi thất lạc, có thể tạo **nhiều executions**; Workflows/Java phải tự dedup.

### 14.3. Bằng chứng hoàn thành

| Câu hỏi | Bằng chứng |
|---|---|
| Trigger có chạy đúng kỳ và múi giờ? | Scheduler logs, scheduled time |
| Workflows/Job có hoàn tất? | Execution status và logs |
| DB có đúng một kỳ đóng sổ? | Unique businessDate/transaction audit |
| Đã publish DAILY_CLOSED một lần về nghiệp vụ? | Outbox/event ID và subscriber dedup |
| Có báo cáo trước SLO? | Business completion timestamp |
| Khi retry có bị trùng không? | Test crash sau DB commit trước HTTP success |
| Chi phí có hợp lý? | Billing/cost theo kỳ và số retries |

## 15. Bài tập thực hành và tự đánh giá

### Bài 1 — Cron và timezone

Viết cron cho: (a) 08:30 thứ Hai–thứ Sáu giờ Việt Nam; (b) 00:00 ngày đầu tháng theo UTC; (c) mỗi 15 phút.

**Gợi ý:** `30 8 * * 1-5` + `Asia/Ho_Chi_Minh`; `0 0 1 * *` + `Etc/UTC`; `*/15 * * * *`.

### Bài 2 — DST

Một hệ thống đặt `0 2 * * *` ở timezone có DST. Tới ngày đổi giờ, lịch đôi khi không chạy đúng như kỳ vọng. Tại sao? Đề xuất cách giảm rủi ro.

**Gợi ý:** lịch dựa wall clock; dùng UTC hoặc định nghĩa nghiệp vụ rõ khi giờ địa phương lặp/mất.

### Bài 3 — Caller identity

Scheduler gọi private Cloud Run và nhận 403. Deployer có `roles/cloudscheduler.admin` nhưng job caller SA không có role trên target.

**Hỏi:** cần cấp role nào cho **principal nào, trên resource nào**? Có nên mở `allUsers` không?

**Gợi ý:** `roles/run.invoker` cho job caller SA trên Cloud Run service, không mở public.

### Bài 4 — OIDC hay OAuth?

Scheduler gọi (a) `https://SERVICE_HOST/internal/close-day` và (b) `https://run.googleapis.com/v2/.../jobs/nightly-batch:run`. Mỗi đích cần token gì?

**Gợi ý:** OIDC cho Cloud Run service, OAuth cho Google API.

### Bài 5 — Mất HTTP response

Java cập nhật DB rồi trả 204 nhưng response bị mất. Scheduler retry cùng kỳ, có thể cập nhật DB hai lần. Thiết kế bảng/key và transaction để tránh.

**Gợi ý:** `jobName + scheduleTime` hoặc `businessDate`, unique constraint và commit atomically.

### Bài 6 — Chạy thủ công

Operator chạy `gcloud scheduler jobs run` trước kỳ 18:00; target dùng scheduleTime làm key dedup. Có thể xảy ra vấn đề gì cho kỳ 18:00 thật?

**Gợi ý:** manual run có thể dùng scheduleTime của kỳ kế tiếp hoặc thiếu header; thiết kế run ID riêng cho test/backfill.

### Bài 7 — Công việc 45 phút

Java batch tính hóa đơn mất 45 phút và được chạy qua Scheduler HTTP trực tiếp. Những giới hạn/risks nào xuất hiện? Chọn kiến trúc thay thế.

**Gợi ý:** HTTP attempt deadline tối đa 30 phút, retries và duplicate side effects; Cloud Run Jobs và/hoặc Workflows.

### Bài 8 — Pub/Sub target “thành công”

Scheduler publish message thành công, nhưng consumer Java trên GKE OOM và Pub/Sub backlog tăng. Scheduler dashboard vẫn success. Có mâu thuẫn không?

**Gợi ý:** không; Scheduler chỉ xác nhận publish, phải giám sát Pub/Sub subscription/consumer riêng.

### Bài 9 — Retry và kỳ lịch

Một job mỗi 5 phút, target phản hồi sau 12 phút hoặc timeout và retry lâu. Kỳ mới có đảm bảo được kích hoạt đúng phút không? Tại sao cần durable claim?

**Gợi ý:** kỳ kế tiếp có thể bị trì hoãn/bỏ qua; backend cũ có thể vẫn xử lý sau timeout.

### Bài 10 — Thiết kế SLO cuối ngày

Xây dựng kiến trúc để Java chốt đơn và publish sự kiện trước 07:00 hôm sau. Nêu **Scheduler cron/timezone, Workflows/Cloud Run Job, IAM, idempotency, monitoring, retry và khôi phục**.

**Gợi ý:** đo business completion và side effects, không chỉ HTTP success của Scheduler.

## 16. Checklist đưa lên production

- [ ] Đã chọn **Cloud Scheduler** cho tác vụ lặp theo lịch; không nhầm với Cloud Tasks một lần.
- [ ] Cron 5 trường được kiểm chứng, có **timezone IANA** rõ và xét DST.
- [ ] Target HTTP/PubSub/App Engine phù hợp nhu cầu và giới hạn location/network.
- [ ] Tách **deployer, job caller SA, Scheduler service agent, runtime SA**.
- [ ] HTTP Cloud Run private dùng **OIDC + Invoker**; Google APIs dùng **OAuth**.
- [ ] OIDC audience đúng service URL, không lẫn query string.
- [ ] Không dùng service account key/token hardcode; không gán Editor/Owner rộng.
- [ ] Đã kiểm tra Scheduler service agent còn `roles/cloudscheduler.serviceAgent`.
- [ ] Handler Java trả 2xx **sau khi ghi kết quả bền vững** hoặc durable enqueue.
- [ ] Có durable idempotency cho retry và manual/backfill; không chỉ dùng header như credential.
- [ ] Attempt deadline, retryCount, min/max backoff được chọn theo SLO; không để HTTP chạy quá 30 phút.
- [ ] Tác vụ dài được chuyển sang **Cloud Run Jobs/Workflows** và theo dõi **execution status**.
- [ ] Pub/Sub target có subscription/consumer metrics, DLQ và retry riêng.
- [ ] Đã thử timeout, response lost, 403, 429/503, duplicate và crash sau commit.
- [ ] Có alerts cho Scheduler attempts thất bại, Cloud Run/Job/Workflow errors và business SLO.
- [ ] Có IaC/config review, owner, log retention, audit IAM và rollback.
- [ ] Đã dự toán Scheduler, compute, Pub/Sub/Workflows, database, logging, egress và retries.
- [ ] Cleanup sandbox chỉ sau khi xác nhận ownership; không xóa job/queue shared.

## 17. Tài liệu Google Cloud chính thức

Các flags, limits, prices và cách tích hợp có thể thay đổi. Đối chiếu trước khi triển khai:

- [Cloud Scheduler — Overview](https://docs.cloud.google.com/scheduler/docs/overview)
- [Cloud Scheduler — Create and manage cron jobs](https://docs.cloud.google.com/scheduler/docs/creating)
- [Cloud Scheduler — Cron job schedules and time zones](https://docs.cloud.google.com/scheduler/docs/configuring/cron-job-schedules)
- [Cloud Scheduler — HTTP target authentication](https://docs.cloud.google.com/scheduler/docs/http-target-auth)
- [Cloud Scheduler — Deduplicate job requests](https://docs.cloud.google.com/scheduler/docs/configuring/deduplicate-job-requests)
- [Cloud Scheduler — Configure retry jobs](https://docs.cloud.google.com/scheduler/docs/configuring/retry-jobs)
- [Cloud Scheduler — Troubleshoot jobs](https://docs.cloud.google.com/scheduler/docs/troubleshooting)
- [Cloud Scheduler — IAM access control](https://docs.cloud.google.com/scheduler/docs/access-control)
- [Cloud Scheduler — Quotas and limits](https://docs.cloud.google.com/scheduler/quotas)
- [Cloud Scheduler — gcloud HTTP job reference](https://docs.cloud.google.com/sdk/gcloud/reference/scheduler/jobs/create/http)
- [Cloud Run — Running services on a schedule](https://docs.cloud.google.com/run/docs/triggering/using-scheduler)
- [Cloud Run — Execute jobs on a schedule](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule)
- [Workflows — Schedule workflow execution](https://docs.cloud.google.com/workflows/docs/schedule-workflow)
- [Cloud Tasks — Overview](https://docs.cloud.google.com/tasks/docs/overview)
- [Cloud Scheduler pricing](https://cloud.google.com/scheduler/pricing)

**Điểm cần nhớ:** **Cloud Scheduler kích hoạt tác vụ theo lịch; nó không thực thi mã Java thay bạn.** Chọn **HTTP, Pub/Sub, Cloud Run Job hoặc Workflows** theo thời gian chạy và mức điều phối cần thiết. Định nghĩa cron/timezone rõ, **OIDC hoặc OAuth đúng loại target**, và luôn bảo vệ nghiệp vụ bằng **durable idempotency** vì Scheduler có thể gửi lại cùng kỳ. Chỉ đánh giá thành công khi **công việc thực tế hoàn tất, đạt SLO và không tạo side effect trùng** — không phải chỉ khi Cloud Scheduler trả “Success”.
