# Tài liệu hóa cách chạy cục bộ, điều tra lỗi và phục hồi

Một hướng dẫn chạy cục bộ tốt giúp thành viên mới khởi động dự án mà không phải hỏi nhiều người, giúp developer tái hiện lỗi trước khi đẩy code và giúp nhóm phân biệt lỗi do ứng dụng với lỗi do môi trường. Trong quy trình CI/CD, tài liệu này còn là cầu nối giữa máy phát triển và runner: cùng phiên bản toolchain, cùng cấu hình cần thiết, cùng lệnh kiểm tra và cùng cách thu thập bằng chứng.

Tài liệu không nên chỉ liệt kê một lệnh chạy ứng dụng. Nó cần giải thích điều kiện đầu vào, cách chuẩn bị dịch vụ phụ thuộc, cấu hình theo môi trường, thứ tự khởi động, cách chạy test, vị trí log, cách nhận diện lỗi thường gặp và quy trình phục hồi khi tiến trình hoặc dữ liệu ở trạng thái không rõ.

Bài viết trình bày cách xây dựng tài liệu local development có thể lặp lại cho một dự án CI/CD, đặc biệt phù hợp với ứng dụng Java dùng Gradle hoặc Maven và các dependency chạy bằng container. Các nguyên tắc cũng áp dụng cho dự án dùng ngôn ngữ hoặc build system khác.

## 1. Mục tiêu của tài liệu chạy cục bộ

Một thành viên mới nên có thể làm theo tài liệu để:

- Kiểm tra máy có đủ công cụ và phiên bản cần thiết.
- Lấy đúng source code và branch.
- Chuẩn bị cấu hình local mà không làm lộ secret.
- Khởi động database, message broker hoặc dịch vụ phụ thuộc.
- Build và chạy ứng dụng.
- Chạy unit test, integration test và các quality checks.
- Xem log và xác định request/job gây lỗi.
- Tái hiện lỗi bằng dữ liệu và điều kiện có thể mô tả.
- Dừng tiến trình, phục hồi môi trường và tiếp tục công việc.
- Tạo báo cáo đủ ngữ cảnh để người khác hỗ trợ.

Tài liệu cũng phải phân biệt thao tác an toàn với thao tác có thể xóa dữ liệu. Ví dụ, restart ứng dụng thường không làm mất database volume; xóa volume có thể xóa toàn bộ dữ liệu local. Người đọc cần biết rõ tác động trước khi chạy lệnh.

## 2. Cấu trúc một trang hướng dẫn local development

Một tài liệu dễ dùng nên theo thứ tự mà người đọc thực hiện:

1. Mục đích, phạm vi và owner.
2. Kiến trúc local và các dependency.
3. Yêu cầu phần mềm, phiên bản và tài nguyên.
4. Cách clone/checkout source.
5. Cách cấu hình biến môi trường và secret.
6. Cách khởi động dịch vụ phụ thuộc.
7. Cách build, run và test.
8. Cách kiểm tra ứng dụng đã sẵn sàng.
9. Vị trí log, metric và trace.
10. Cách điều tra các lỗi thường gặp.
11. Cách dừng, phục hồi và reset môi trường.
12. Cách thu thập evidence và yêu cầu hỗ trợ.

Mỗi bước nên có lệnh cụ thể, kết quả mong đợi và cách xử lý khi kết quả khác dự kiến. Tránh viết "cấu hình database như bình thường" hoặc "chạy test như thường lệ" vì người mới không biết trạng thái nào được xem là bình thường.

### Mẫu thông tin đầu tài liệu

| Trường | Nội dung cần ghi |
|---|---|
| Service/repository | Tên dịch vụ và repository |
| Owner | Team chịu trách nhiệm |
| Supported OS | Windows, macOS, Linux hoặc phạm vi được hỗ trợ |
| Toolchain | JDK, Gradle/Maven, Docker và phiên bản |
| Local ports | Port ứng dụng và dependency |
| Required services | Database, broker, mock service |
| Startup command | Lệnh khởi động chuẩn |
| Test command | Lệnh kiểm tra chuẩn |
| Health endpoint | Cách xác minh sẵn sàng |
| Documentation owner | Người cập nhật tài liệu |

Tài liệu cần có ngày hoặc phiên bản kiểm chứng. Khi toolchain hoặc cách chạy thay đổi, owner phải cập nhật hướng dẫn cùng thay đổi code.

## 3. Kiểm tra toolchain và phiên bản

Lỗi local thường bắt đầu từ khác biệt phiên bản. Máy developer có thể dùng JDK mới hơn runner, Docker Compose cũ hơn hoặc build tool cài toàn cục khác với dự án.

Ưu tiên wrapper và version file được repository quản lý:

- Gradle Wrapper thay vì phụ thuộc Gradle cài toàn cục.
- Maven Wrapper thay vì phụ thuộc Maven cài toàn cục.
- Toolchain declaration để chọn JDK compile/test.
- .java-version, .tool-versions hoặc cấu hình tương đương nếu dự án sử dụng.
- Docker Compose plugin version được hỗ trợ.
- Node/Python tool version file nếu pipeline có bước frontend hoặc script phụ trợ.

Ví dụ kiểm tra:

~~~powershell
java -version
.\gradlew.bat --version
docker version
docker compose version
git --version
~~~

Trên macOS/Linux:

~~~bash
java -version
./gradlew --version
docker version
docker compose version
git --version
~~~

Nếu dự án dùng Maven Wrapper:

~~~powershell
.\mvnw.cmd -version
~~~

~~~bash
./mvnw -version
~~~

Không chỉ ghi "cần Java 21". Hãy ghi rõ JDK distribution/version được hỗ trợ và cách xác minh wrapper đang sử dụng đúng toolchain. Khi có nhiều JDK, chỉ cách kiểm tra JAVA_HOME và PATH mà không yêu cầu người đọc thay đổi global setting tùy tiện.

## 4. Lấy source code và xác định đúng revision

Bước đầu tiên là làm việc trên đúng repository, branch và commit.

~~~bash
git clone <repository-url>
cd <repository-directory>
git status --short
git branch --show-current
git rev-parse HEAD
~~~

Trước khi debug, ghi nhận:

- Branch hiện tại.
- Commit SHA.
- Có file chưa commit hoặc thay đổi local không.
- Có submodule hoặc generated source cần khởi tạo không.
- Có patch hoặc local configuration riêng không.

Nếu cần so sánh với CI, dùng đúng commit SHA của workflow run. Không so sánh kết quả local trên source đã chỉnh sửa với pipeline chạy trên commit cũ rồi kết luận hai môi trường khác nhau.

Khi thử nghiệm một thay đổi độc lập, có thể dùng worktree để giữ working tree hiện tại:

~~~bash
git worktree add ../service-debug-worktree <commit-or-branch>
~~~

Sau khi hoàn tất, kiểm tra đường dẫn worktree trước khi remove. Không dùng lệnh reset hoặc clean để "làm sạch" repository khi chưa biết thay đổi nào thuộc về người khác.

## 5. Cấu hình local và thứ tự ưu tiên

Ứng dụng thường nhận cấu hình từ nhiều nguồn:

- Giá trị mặc định trong code.
- File cấu hình chung.
- File profile local.
- Environment variables.
- Secret manager hoặc secret được cấp khi chạy.
- Tham số command line.

Tài liệu phải mô tả nguồn nào có độ ưu tiên cao hơn. Ví dụ, environment variable có thể ghi đè giá trị trong application-local.yml. Nếu không nói rõ, người đọc có thể sửa file nhưng ứng dụng vẫn dùng giá trị từ shell.

### Dùng file mẫu thay vì commit cấu hình riêng

Có thể cung cấp .env.example hoặc application-local.example.yml với giá trị minh họa:

~~~dotenv
APP_PROFILE=local
SERVER_PORT=8080
DB_HOST=localhost
DB_PORT=5432
DB_NAME=app_local
DB_USER=app
DB_PASSWORD=local-only-change-me
~~~

Đây là placeholder chỉ dành cho môi trường local dùng một lần; dự án thật nên hướng dẫn tạo secret local riêng. File chứa credential thật cần được ignore bởi Git và không được đưa vào artifact hoặc log.

Không đặt password production hoặc token dùng chung vào ví dụ. Nếu cần truy cập service dùng chung, hãy chỉ cách lấy credential từ secret manager và giới hạn quyền.

### Kiểm tra cấu hình trước khi chạy

Ứng dụng nên validate các biến bắt buộc khi khởi động và báo tên biến còn thiếu mà không in giá trị secret. Ví dụ:

~~~text
Configuration error:
- DB_HOST is missing
- APP_PROFILE must be one of: local, test
No credentials were printed.
~~~

Tài liệu nên có bảng biến môi trường:

| Biến | Bắt buộc | Ví dụ local | Mô tả |
|---|---|---|---|
| APP_PROFILE | Có | local | Profile cấu hình |
| SERVER_PORT | Không | 8080 | Port HTTP |
| DB_HOST | Có | localhost | Database host |
| DB_PORT | Có | 5432 | Database port |
| DB_NAME | Có | app_local | Database local |
| DB_USER | Có | app | User local |
| DB_PASSWORD | Có | Lấy từ local secret | Không ghi vào Git |

## 6. Quản lý secret trong môi trường phát triển

Secret local vẫn cần được bảo vệ. Một token thử nghiệm có thể cấp quyền tới cloud hoặc dịch vụ nội bộ thật.

Quy tắc nên được ghi rõ:

- Không commit .env, private key, token hoặc file credential.
- Không paste secret vào issue, chat hoặc log.
- Dùng credential riêng cho local, không tái sử dụng production credential.
- Cấp quyền tối thiểu và đặt thời hạn.
- Rotate hoặc thu hồi credential khi nghi ngờ bị lộ.
- Không dùng secret thật trong test fixture.
- Kiểm tra Git status trước khi commit.
- Redact header Authorization, cookie và connection string khi chia sẻ log.

Có thể kiểm tra file bị theo dõi nhầm:

~~~bash
git status --short
git check-ignore -v .env
~~~

Nếu file secret đã được commit, xóa file ở commit mới không làm secret cũ an toàn trở lại. Cần thu hồi/rotate secret và xử lý lịch sử repository theo quy trình bảo mật của tổ chức.

## 7. Khởi động dependency bằng Docker Compose

Nhiều service cần database, Redis, Kafka hoặc mock server. Docker Compose giúp chuẩn hóa dependency local mà không bắt mọi developer cài từng dịch vụ trực tiếp.

Ví dụ compose tối giản cho PostgreSQL:

~~~yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: app_local
      POSTGRES_USER: app
      POSTGRES_PASSWORD: local-only-change-me
    ports:
      - "5432:5432"
    volumes:
      - app-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  app-db-data:
~~~

Ví dụ này chỉ là mẫu local, không dùng password này ở môi trường chia sẻ. Dự án cần pin image tag hoặc digest theo policy và chọn volume/port phù hợp.

Khởi động và kiểm tra:

~~~bash
docker compose up -d --wait
docker compose ps
docker compose logs --tail=100 db
~~~

Tùy phiên bản Docker Compose, tùy chọn `--wait` có thể chưa được hỗ trợ. Khi gặp lỗi không nhận diện tùy chọn này, dùng `docker compose up -d`, sau đó kiểm tra health status bằng `docker compose ps` và chờ service đạt trạng thái healthy trước khi chạy ứng dụng.

Dừng container:

~~~bash
docker compose stop
~~~

Dừng và xóa container/network nhưng giữ named volume:

~~~bash
docker compose down
~~~

Lệnh sau xóa cả named volume và dữ liệu local trong volume:

~~~bash
docker compose down -v
~~~

Chỉ dùng down -v khi đã xác nhận dữ liệu trong volume có thể bỏ, hoặc đã export/backup cần thiết. Tài liệu phải đánh dấu rõ lệnh reset dữ liệu và không đặt nó trong quy trình khởi động thông thường.

## 8. Thứ tự khởi động và readiness

Container ở trạng thái running chưa chắc dịch vụ đã sẵn sàng nhận request. Database có thể đang recovery, broker đang tạo metadata hoặc migration chưa hoàn tất.

Quy trình chuẩn nên là:

1. Khởi động dependency.
2. Chờ health check đạt.
3. Kiểm tra kết nối từ host hoặc container ứng dụng.
4. Chạy migration nếu quy trình local yêu cầu.
5. Khởi động ứng dụng.
6. Kiểm tra health/readiness endpoint.
7. Thực hiện một smoke test nhỏ.

Không dùng sleep cố định dài làm cơ chế duy nhất để chờ dependency. Hãy dùng health check hoặc retry có deadline. Nếu readiness không đạt, in trạng thái container và log liên quan để người dùng biết đang chờ điều gì.

Ví dụ kiểm tra PostgreSQL từ host:

~~~bash
pg_isready -h localhost -p 5432 -U app -d app_local
~~~

Nếu không có client cài local, có thể chạy công cụ kiểm tra trong container hoặc dùng health status của Compose.

## 9. Build và chạy ứng dụng Java

Ưu tiên lệnh wrapper để dùng đúng phiên bản build tool của repository.

### Gradle

Build và chạy unit test:

~~~bash
./gradlew clean test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

Tạo artifact:

~~~bash
./gradlew build
~~~

Chạy ứng dụng nếu dự án dùng Spring Boot Gradle plugin:

~~~bash
./gradlew bootRun
~~~

Nếu dự án có nhiều module, tài liệu phải ghi đúng task path, ví dụ :service-api:test hoặc :service-api:bootRun. Không yêu cầu người đọc đoán module từ tên folder.

### Maven

Chạy verification:

~~~bash
./mvnw -B verify
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd -B verify
~~~

Chạy ứng dụng Spring Boot nếu plugin được cấu hình:

~~~bash
./mvnw spring-boot:run
~~~

Không giả định mọi dự án Java đều dùng Spring Boot. Lệnh thực tế cần theo build file và plugin mà repository khai báo.

### Tách build và run

Tài liệu nên nói rõ lệnh nào compile/test, lệnh nào khởi động ứng dụng, lệnh nào tạo artifact release. Điều này giúp developer không vô tình chạy cả publish/deploy khi chỉ muốn kiểm tra local.

## 10. Chạy ứng dụng với profile local

Profile local nên mô phỏng dependency và hành vi cần thiết nhưng không tự động cấp quyền production.

Ví dụ Spring Boot:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=local'
~~~

Hoặc qua environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=local ./gradlew bootRun
~~~

Trên PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
.\gradlew.bat bootRun
~~~

Profile local có thể dùng database local, mock external service và log level phù hợp. Không nên tự động tắt authentication hoặc authorization nếu việc đó làm test không còn phản ánh behavior quan trọng.

Nếu cần mock service, ghi rõ endpoint, cách khởi động và những khác biệt so với môi trường thật.

## 11. Chạy các tầng kiểm thử

Một tài liệu local cần phân biệt test nhanh và test đầy đủ:

| Loại test | Mục đích | Dependency |
|---|---|---|
| Unit test | Kiểm tra logic riêng lẻ | Thường không cần dịch vụ ngoài |
| Component test | Kiểm tra một thành phần với dependency được cô lập | Mock hoặc container riêng |
| Integration test | Kiểm tra tương tác giữa các thành phần | Database/broker/service |
| Contract test | Kiểm tra hợp đồng API/message | Provider/consumer contract |
| End-to-end test | Kiểm tra luồng nghiệp vụ xuyên hệ thống | Nhiều dịch vụ |
| Smoke test | Xác minh ứng dụng vừa khởi động có hoạt động cơ bản | Ứng dụng và dependency |

Chạy nhanh unit test trước khi chạy bộ integration lớn. Nếu lỗi chỉ xuất hiện khi có database, hãy khởi động dependency tương ứng và chạy đúng test suite.

Với Gradle, có thể dùng task cụ thể nếu project đã khai báo:

~~~bash
./gradlew test
./gradlew integrationTest
~~~

Với Maven, có thể dùng profile hoặc plugin đã cấu hình trong project:

~~~bash
./mvnw -B test
./mvnw -B verify
~~~

Không tự đặt tên task/profile trong tài liệu nếu repository chưa định nghĩa chúng. Owner phải xác minh các lệnh trước khi công bố.

## 12. Đảm bảo local và CI có cùng ý nghĩa kiểm tra

Mục tiêu không phải làm local giống runner ở mọi chi tiết, mà là bảo đảm cùng một lệnh kiểm tra có semantics tương đương.

So sánh:

- JDK và build tool version.
- Dependency lock và repository configuration.
- Environment variables bắt buộc.
- Test profile và test selection.
- Database/broker version.
- Locale, timezone và encoding.
- Container image và architecture.
- Feature flags và config revision.
- Cách tạo artifact.
- Lệnh quality/security checks.

Nếu CI chạy ./gradlew --no-daemon clean verify, local nên có lệnh tương ứng và tài liệu giải thích khác biệt có chủ đích. Không nên có một script local chỉ chạy subset test nhưng được mô tả là "giống CI".

### Dùng script chung khi có thể

Có thể tạo script task-level được cả local và CI gọi, ví dụ:

~~~bash
./scripts/verify.sh
~~~

Script cần:

- Kiểm tra prerequisite.
- Dùng wrapper.
- Chạy đúng test/check.
- Trả exit code khác 0 khi thất bại.
- Không phụ thuộc shell state của một máy cụ thể.
- Không in secret.
- Ghi rõ output report ở đâu.

Nếu cần hỗ trợ Windows, cung cấp PowerShell script tương đương hoặc dùng script portable phù hợp.

## 13. Kiểm tra health endpoint và kết nối

Sau khi ứng dụng khởi động, kiểm tra readiness thay vì chỉ nhìn thấy log "Started".

Ví dụ:

~~~bash
curl -fsS http://localhost:8080/actuator/health
~~~

Nếu endpoint yêu cầu authentication hoặc không được bật trong local, tài liệu cần chỉ ra cách kiểm tra phù hợp. Không bật endpoint nhạy cảm ra public interface chỉ để tiện debug.

Kiểm tra port đang lắng nghe:

PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen
~~~

macOS/Linux:

~~~bash
lsof -iTCP:8080 -sTCP:LISTEN
~~~

Nếu port đã được sử dụng, xác định process owner trước khi dừng. Không kill process theo PID mà chưa xác minh đó là process do mình khởi chạy.

## 14. Vị trí log và cách đọc log

Tài liệu phải nói log nằm ở đâu:

- Terminal đang chạy ứng dụng.
- File log local nếu app được cấu hình ghi file.
- Docker Compose service logs.
- Test report và build output.
- IDE run console.
- Local observability collector nếu có.

Ví dụ:

~~~bash
docker compose logs --since=10m db
docker compose logs -f db
~~~

Với ứng dụng chạy trực tiếp, dùng terminal đã khởi chạy hoặc file log được cấu hình. Với Gradle, test report thường nằm trong build/reports/tests hoặc đường dẫn được build script định nghĩa.

### Log có cấu trúc

Khi có thể, log nên chứa:

- Timestamp có timezone rõ.
- Log level.
- Service và environment.
- Request/correlation ID.
- Trace ID.
- Pipeline run/job ID nếu được gọi từ CI.
- Operation ID.
- Event name và error code.

Không log password, token, authorization header hoặc payload nhạy cảm. Trước khi gửi log cho người khác, lọc bỏ secret và dữ liệu cá nhân.

## 15. Quy trình điều tra lỗi có hệ thống

Khi gặp lỗi, tránh thay đổi nhiều thứ cùng lúc. Dùng trình tự:

1. Ghi nhận hành động vừa thực hiện và lệnh chính xác.
2. Lấy commit SHA và trạng thái working tree.
3. Xác định lỗi đầu tiên trong log, không chỉ lỗi cuối cùng.
4. Xác định thành phần liên quan: build tool, ứng dụng, database, broker, network hay credential.
5. So sánh cấu hình thực tế với cấu hình mong đợi.
6. Tái hiện bằng lệnh nhỏ nhất có thể.
7. Thay đổi một yếu tố mỗi lần.
8. Kiểm tra lại bằng test hoặc health check.
9. Ghi nguyên nhân và cách phục hồi.
10. Cập nhật tài liệu nếu phát hiện bước còn thiếu.

### Phân biệt lỗi gốc và lỗi dây chuyền

Ví dụ database không khởi động có thể kéo theo:

- Connection refused.
- Repository initialization failed.
- Application context failed.
- Health endpoint không sẵn sàng.
- Integration test timeout.

Lỗi gốc là database chưa sẵn sàng. Không nên xử lý từng stack trace ở tầng ứng dụng như năm lỗi độc lập.

Tìm lỗi đầu tiên theo timeline và kiểm tra dependency upstream.

## 16. Phân loại lỗi thường gặp

| Nhóm lỗi | Dấu hiệu | Kiểm tra đầu tiên |
|---|---|---|
| Toolchain | Unsupported class version, task không tồn tại | JDK, wrapper và build plugin |
| Dependency | Could not resolve artifact, checksum mismatch | Repository, proxy, lockfile và network |
| Configuration | Missing property, invalid profile | Environment variables và config precedence |
| Port/network | Connection refused, address already in use | Service health, port và DNS |
| Database | Authentication failed, schema missing, migration error | Host/port/user, database state và migration history |
| Container | Image pull failed, container unhealthy | Registry access, image tag và container logs |
| Test | Assertion failure, flaky timeout | Test data, isolation, clock và dependency |
| Permission | 401/403, access denied | Identity, token scope và role |
| Resource | Out of memory, disk full, process killed | Heap, container limits, disk và concurrency |
| Runtime | Deadlock, thread starvation, high latency | Thread dump, pool metrics và dependency |
| CI/local drift | Local pass nhưng CI fail | Toolchain, OS, env, architecture và test selection |

Mỗi lỗi trong tài liệu nội bộ nên có: triệu chứng, nguyên nhân phổ biến, lệnh kiểm tra, cách khắc phục và tiêu chí xác nhận đã phục hồi.

## 17. Điều tra lỗi build và dependency

Khi build fail:

1. Xác minh wrapper và JDK.
2. Đọc lỗi đầu tiên, không chỉ summary cuối.
3. Xác định task/module thất bại.
4. Kiểm tra repository/proxy và dependency lock.
5. Chạy lại task nhỏ nhất để tái hiện.
6. Chỉ refresh dependency khi có bằng chứng cache/repository bị stale.

Gradle:

~~~bash
./gradlew test --stacktrace
./gradlew test --info
./gradlew --stop
~~~

Maven:

~~~bash
./mvnw -B -e test
~~~

Không bật debug log toàn diện ngay từ đầu trong môi trường có secret. Một số build plugin có thể in URL, header hoặc property nhạy cảm. Nếu cần mức log sâu hơn, hãy kiểm tra và redaction trước khi chia sẻ.

Không xóa toàn bộ cache ngay khi gặp lỗi dependency. Cache có thể lớn và việc xóa làm mất thời gian tải lại, đồng thời che giấu nguyên nhân repository/proxy. Hãy thử task cụ thể, kiểm tra dependency metadata và dùng refresh có chủ đích.

## 18. Điều tra database và migration

Khi ứng dụng không kết nối được database, kiểm tra theo thứ tự:

1. Container/service có running không?
2. Health check có pass không?
3. Host và port có đúng từ góc nhìn của process ứng dụng không?
4. Database name và user có tồn tại không?
5. Credential local có đúng không?
6. Database có chấp nhận kết nối từ interface đó không?
7. Schema/migration version có phù hợp không?
8. Connection pool có hết connection hoặc giữ connection lâu không?

Đừng mặc định localhost có cùng ý nghĩa trong host và container. Từ host, localhost có thể trỏ tới port publish của Compose; từ container app, database thường được gọi bằng service name như db trên Docker network.

### Migration fail

Nếu migration thất bại:

- Đọc migration ID và error đầu tiên.
- Kiểm tra migration history.
- Xác định transaction đã commit một phần hay chưa.
- Kiểm tra schema thực tế.
- Không tự xóa migration history để ép chạy lại.
- Không sửa migration đã áp dụng ở môi trường chia sẻ.
- Dùng migration mới hoặc recovery procedure phù hợp.
- Backup dữ liệu trước thao tác sửa có rủi ro.

Nếu không chắc migration đã chạy tới đâu, dừng thao tác ghi tiếp và đối soát schema/history trước khi rerun.

## 19. Điều tra container, network và port

Một số lỗi phổ biến:

- Container không start do image pull hoặc cấu hình.
- Port trên host đã bị process khác sử dụng.
- App container không resolve được hostname dependency.
- Service healthy nhưng app dùng sai credential.
- Container bị restart do OOM.
- DNS/proxy/firewall chặn dependency.
- Host architecture không tương thích image.

Các lệnh kiểm tra:

~~~bash
docker compose ps
docker compose logs --tail=200 <service>
docker inspect <container-id>
docker stats
docker network ls
~~~

Kiểm tra network từ container app nếu image có công cụ phù hợp. Nếu không, dùng ephemeral debug container trong cùng network theo policy của dự án.

Lệnh `docker inspect` có thể hiển thị environment variables, mount path và thông tin cấu hình. Chỉ xem output trong môi trường có quyền phù hợp; redaction trước khi gửi cho teammate hoặc đính kèm ticket.

Không kết luận "database down" chỉ từ connection refused ở app. Kiểm tra port mapping, hostname và network namespace trước.

## 20. Điều tra lỗi runtime Java

Khi ứng dụng khởi động nhưng phản hồi chậm hoặc treo, cần phân biệt CPU cao, thread bị block, connection pool cạn, deadlock và dependency chậm.

Các công cụ hữu ích:

~~~bash
jcmd <pid> Thread.print
jcmd <pid> GC.heap_info
jcmd <pid> VM.system_properties
~~~

System properties có thể chứa URL, user hoặc giá trị cấu hình nhạy cảm. Chỉ thu thập khi cần, rà soát và redaction output trước khi chia sẻ. Thread dump cũng cần được kiểm tra để tránh phát tán thông tin request hoặc dữ liệu nghiệp vụ.

Các thông tin cần xem:

- Thread state và stack.
- Thread pool active/queue/rejected.
- Database connection pool active/idle/pending.
- HTTP client connection pool.
- Heap usage và garbage collection.
- Request latency và error rate.
- Dependency latency.
- Deadlock detection.
- Container memory/CPU limit.

Chỉ thu thập heap dump khi có đủ disk và quyền xử lý file đó; heap dump có thể chứa dữ liệu nhạy cảm. Không đưa file dump lên ticket công khai.

## 21. Tái hiện lỗi một cách có thể lặp lại

Một bug report hữu ích phải mô tả điều kiện tái hiện:

- Commit SHA.
- OS và architecture.
- JDK/build tool version.
- Profile/config revision.
- Dependency version.
- Dữ liệu fixture hoặc test case.
- Lệnh chính xác.
- Thời điểm và timezone nếu liên quan.
- Kết quả mong đợi.
- Kết quả thực tế.
- Tần suất tái hiện.
- Log/trace đã redacted.

Giảm phạm vi tái hiện:

- Chạy một test thay vì toàn bộ suite.
- Dùng một record fixture thay vì dataset lớn.
- Dùng một endpoint thay vì toàn workflow.
- Tắt các dependency không liên quan bằng mock/test container.
- Cố định clock, timezone hoặc random seed khi phù hợp.

Không chỉnh code và cấu hình cùng lúc trong khi điều tra. Nếu lỗi biến mất, bạn sẽ không biết thay đổi nào đã tác động.

## 22. Quy trình phục hồi khi môi trường local bị lỗi

Phục hồi nên đi từ ít tác động tới nhiều tác động:

1. Xác định process hoặc service đang lỗi.
2. Lưu log và trạng thái trước khi thay đổi.
3. Dừng đúng process do mình sở hữu.
4. Kiểm tra dependency và health status.
5. Restart ứng dụng.
6. Nếu cần, restart riêng dependency bị lỗi.
7. Xác minh config và credential.
8. Kiểm tra checkpoint hoặc migration state nếu tác vụ bị ngắt.
9. Chỉ reset dữ liệu local sau khi xác nhận có thể bỏ.
10. Chạy smoke test và test liên quan.
11. Ghi nhận trạng thái cuối và nguyên nhân.

Ví dụ dừng Compose service cụ thể:

~~~bash
docker compose stop db
docker compose up -d db
docker compose ps
~~~

Nếu ứng dụng chạy trực tiếp, dừng bằng terminal hoặc process manager đã khởi chạy nó. Tránh kill mọi process Java vì có thể dừng IDE hoặc ứng dụng khác.

### Khi nào cần reset?

Reset có thể phù hợp khi volume local hỏng hoặc fixture không còn nhất quán. Trước khi reset:

- Xác định đúng Compose project và volume.
- Kiểm tra dữ liệu có cần giữ không.
- Export/backup nếu cần.
- Xác nhận đây là local disposable environment.
- Ghi lại lệnh reset và tác động.
- Sau reset, chạy migration/seed lại và verify.

Không áp dụng lệnh xóa volume local cho staging hoặc production.

## 23. Phục hồi khi CI job hoặc runner bị ngắt

Nếu local run dùng để điều tra một CI failure, cần đối chiếu workflow run:

- Commit SHA và branch.
- Job name và attempt.
- Runner OS/image/architecture.
- Toolchain version.
- Environment variables và profile.
- Artifact digest.
- Test report.
- Exit code và failure classification.
- Dependency service version.

Nếu job bị ngắt giữa thao tác có side effect, kiểm tra trạng thái bên ngoài trước khi rerun. Ví dụ publish có thể đã hoàn tất dù response bị mất; deploy có thể đang rollout dù runner đã bị terminate.

Không coi timeout là bằng chứng thao tác chưa xảy ra. Tra cứu operation ID, package version/digest hoặc observed resource state trước khi gửi lại.

Nếu lỗi chỉ do môi trường runner, tái hiện bằng runner image hoặc container tương đương. Nếu local pass nhưng CI fail, so sánh từng đầu vào thay vì thay đổi code để làm test pass một cách mù quáng.

## 24. Thu thập evidence để handoff

Khi cần nhờ teammate hỗ trợ, gửi một gói thông tin có thể điều tra:

| Thành phần | Nội dung |
|---|---|
| Summary | Một câu mô tả lỗi |
| Commit | SHA và branch |
| Environment | OS, JDK, build tool, profile |
| Command | Lệnh chính xác đã chạy |
| Expected | Kết quả mong đợi |
| Actual | Kết quả thực tế và exit code |
| First failure | Error đầu tiên theo timeline |
| Logs | Đoạn log đã redacted |
| Dependencies | Trạng thái DB/broker/container |
| Reproduction | Các bước tái hiện ngắn nhất |
| Attempts | Số lần, kết quả từng lần |
| Changes tried | Thay đổi đã thử và kết quả |
| Current state | Service/process/data hiện đang ở trạng thái nào |

Đính kèm link tới pipeline run hoặc test report nếu có. Không gửi secret, token, dữ liệu cá nhân hoặc dump chưa được kiểm tra.

Một handoff tốt kết thúc bằng câu hỏi cụ thể, ví dụ: "Có thể xác nhận migration V12 có thể tiếp tục sau lỗi duplicate index trên database local này không?" thay vì chỉ gửi "app không chạy".

## 25. Cập nhật tài liệu sau khi tìm ra nguyên nhân

Một lỗi được giải quyết một lần chưa tạo ra kiến thức dùng lại. Sau điều tra, hãy cập nhật tài liệu:

- Thêm prerequisite bị thiếu.
- Sửa command không đúng hệ điều hành.
- Ghi rõ port/service name.
- Bổ sung expected output.
- Thêm bước kiểm tra trước khi reset.
- Cập nhật version toolchain.
- Ghi rõ lỗi chỉ xảy ra trong một profile.
- Thêm test hoặc health check để ngăn tái diễn.
- Thêm owner và ngày xác minh.

Nếu quy trình đã thay đổi, xóa hướng dẫn cũ hoặc đánh dấu deprecated. Hai cách chạy mâu thuẫn khiến người đọc chọn nhầm và làm lỗi tái xuất hiện.

Tài liệu nên được review cùng pull request thay đổi build, Compose, config hoặc developer scripts. Có thể đặt smoke check cho các lệnh trong hướng dẫn để phát hiện tài liệu lỗi thời.

## 26. Template runbook cho một lỗi thường gặp

Có thể dùng cấu trúc sau để chuẩn hóa các mục troubleshooting:

~~~markdown
### Lỗi: Ứng dụng không kết nối được database local

**Triệu chứng**
- Startup log báo connection refused hoặc authentication failed.
- Health endpoint không đạt readiness.

**Phạm vi**
- Chỉ áp dụng cho profile local.
- Database chạy qua Docker Compose.

**Kiểm tra**
1. Chạy docker compose ps.
2. Kiểm tra health status của service db.
3. Xác minh DB_HOST và DB_PORT từ môi trường ứng dụng.
4. Kiểm tra database/user và credential local.
5. Đọc docker compose logs --tail=100 db.

**Khắc phục**
1. Nếu container chưa chạy, khởi động service db.
2. Nếu credential sai, cập nhật secret local theo hướng dẫn.
3. Nếu port xung đột, xác định process đang giữ port trước khi thay đổi.
4. Chỉ reset volume khi dữ liệu local có thể bỏ.

**Xác minh**
- Database health check pass.
- Ứng dụng kết nối thành công.
- Smoke test đạt.

**Evidence**
- Commit SHA, command, timestamp và log đã redacted.

**Owner**
- Team/service owner và ngày review.
~~~

Mỗi runbook nên chỉ giải quyết một vấn đề cụ thể. Nếu một mục có quá nhiều nhánh, tách thành các mục nhỏ để người đọc dễ theo dõi.

## 27. Anti-pattern khi viết hướng dẫn local và troubleshooting

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ ghi một lệnh start | Người mới thiếu prerequisite và config | Ghi đầy đủ từ kiểm tra toolchain tới readiness |
| Dùng version latest | Local và CI dễ lệch | Pin version hoặc chỉ rõ dải hỗ trợ |
| Commit file .env thật | Lộ credential | Dùng file mẫu và local secret |
| Không ghi profile | Chạy nhầm config hoặc kết nối môi trường thật | Chỉ rõ profile và config precedence |
| Sleep cố định để chờ database | Flaky theo tốc độ máy | Dùng health check và deadline |
| Xóa cache/volume ngay khi lỗi | Mất dữ liệu và che nguyên nhân | Chẩn đoán trước, reset có kiểm soát |
| Chỉ đọc lỗi cuối stack trace | Bỏ lỡ nguyên nhân đầu tiên | Dựng timeline và tìm first failure |
| Kill mọi process Java | Dừng nhầm IDE/service khác | Xác minh PID và owner |
| Bật debug log rồi chia sẻ nguyên trạng | Có thể lộ secret | Dùng log có cấu trúc và redaction |
| Local command khác CI nhưng không ghi rõ | Kết quả không so sánh được | Dùng script chung và mô tả khác biệt |
| Không lưu commit/config revision | Không tái hiện được lỗi | Ghi source và environment identity |
| Hướng dẫn không có owner/review date | Tài liệu lỗi thời | Gắn owner và review cùng code change |

## 28. Checklist trước khi công bố tài liệu

### Chuẩn bị và chạy

- [ ] Ghi rõ OS, JDK, build tool và Docker version.
- [ ] Dùng wrapper hoặc tool version được pin.
- [ ] Có bước clone/checkout và xác minh commit.
- [ ] Có file cấu hình mẫu không chứa secret.
- [ ] Mô tả profile và config precedence.
- [ ] Có dependency startup và health check.
- [ ] Có lệnh build, run, unit test và integration test.
- [ ] Có expected output hoặc cách xác minh readiness.

### Điều tra và phục hồi

- [ ] Có vị trí log, report và cách redaction.
- [ ] Có hướng dẫn tìm first failure.
- [ ] Có bảng lỗi thường gặp và bước kiểm tra.
- [ ] Có cách kiểm tra port, network và dependency.
- [ ] Có quy trình dừng process/service đúng owner.
- [ ] Phân biệt restart, down và xóa volume.
- [ ] Có checkpoint/migration recovery nếu liên quan.
- [ ] Có tiêu chí xác nhận phục hồi thành công.

### Handoff và duy trì

- [ ] Có template report gồm commit, command, environment và evidence.
- [ ] Không đưa secret hoặc dữ liệu nhạy cảm vào tài liệu.
- [ ] Local command có ý nghĩa tương đương CI.
- [ ] Có owner và ngày review.
- [ ] Runbook được cập nhật cùng thay đổi build/config.
- [ ] Các lệnh chính đã được kiểm chứng trên OS được hỗ trợ.

## Kết luận

Tài liệu chạy cục bộ, điều tra lỗi và phục hồi là một phần của chất lượng CI/CD. Hãy mô tả toolchain có phiên bản, cấu hình local có ranh giới secret, dependency có health check, lệnh build/test rõ ràng và cách xác minh readiness. Khi lỗi xảy ra, tìm first failure, tái hiện bằng đầu vào xác định, thay đổi từng yếu tố và chỉ reset dữ liệu sau khi hiểu tác động. Ghi lại commit, môi trường, command, log đã redacted và trạng thái phục hồi để teammate có thể tiếp tục điều tra. Khi tài liệu được review cùng code và pipeline, local development trở nên nhất quán hơn với CI và việc hỗ trợ giữa các thành viên ít phụ thuộc vào kiến thức truyền miệng.

