# Sử dụng container làm môi trường công việc khi phù hợp

Môi trường phát triển và môi trường CI thường khác nhau về hệ điều hành, phiên bản runtime, thư viện hệ thống, công cụ build và dịch vụ phụ trợ. Những khác biệt này có thể khiến một thay đổi chạy tốt trên máy của lập trình viên nhưng thất bại trên runner, hoặc khiến lỗi CI khó tái hiện cục bộ.

Container có thể giúp đóng gói toolchain và các phụ thuộc cần thiết thành một môi trường có thể khởi tạo lại. Lập trình viên và CI có thể dùng cùng image, cùng lệnh build và cùng cấu hình kiểm thử. Tuy nhiên, container không phải lựa chọn mặc định cho mọi dự án. Nó có chi phí về runtime, quản lý image, quyền truy cập, đồng bộ file và cách kết nối với công cụ trên máy chủ.

Nguyên lý cần nắm là chọn container khi nó giải quyết được khác biệt môi trường hoặc giảm đáng kể công sức thiết lập; định nghĩa image và cách chạy bằng mã; giới hạn quyền của container; và giữ quy trình đủ đơn giản để người phát triển có thể làm việc hiệu quả.

## 1. Container là gì trong bối cảnh môi trường phát triển?

Container là một tiến trình được cô lập bằng các cơ chế của hệ điều hành, chẳng hạn namespace và control group trên Linux. Nó sử dụng kernel của máy chủ hoặc môi trường máy ảo bên dưới, trong khi filesystem, tiến trình, mạng và tài nguyên có thể được giới hạn theo cấu hình.

Image là mẫu bất biến dùng để tạo container. Image có thể chứa runtime, thư viện hệ thống, công cụ build và các tệp cần thiết. Container là một lần thực thi từ image, có thể được tạo, dừng, xóa và tạo lại.

Trong công việc phát triển, container thường đảm nhiệm một hoặc nhiều vai trò:

- Cung cấp JDK, Node.js, Python, compiler hoặc công cụ build với phiên bản xác định.
- Cung cấp thư viện hệ thống cần thiết để biên dịch hoặc chạy ứng dụng.
- Chạy database, message broker, cache hoặc dịch vụ phụ trợ phục vụ kiểm thử.
- Tạo môi trường dòng lệnh đồng nhất cho cả lập trình viên và CI.
- Tạo môi trường tạm thời để chạy test hoặc kiểm tra thay đổi trong workspace sạch.

Container không phải máy ảo đầy đủ. Nó không mang theo một kernel riêng và mức cô lập phụ thuộc vào container runtime, cấu hình host và quyền được cấp. Trên Linux, container thường dùng trực tiếp kernel của host. Trên Windows hoặc macOS, Docker Desktop thường sử dụng một máy ảo Linux nhẹ để chạy Linux container. Vì vậy, container giảm nhiều khác biệt về user space nhưng không xóa bỏ mọi khác biệt của hệ điều hành, kiến trúc CPU hoặc filesystem.

## 2. Khi nào nên dùng container?

Container hữu ích khi môi trường có nhiều phụ thuộc hoặc khó chuẩn hóa bằng hướng dẫn cài đặt thông thường.

Một số tình huống phù hợp:

**Toolchain phức tạp hoặc nhiều phiên bản.** Dự án cần một phiên bản JDK cụ thể, compiler native, thư viện hệ thống hoặc CLI riêng. Đóng gói chúng vào image giúp người mới không phải cài từng thành phần theo hướng dẫn thủ công.

**Nhiều dự án cần môi trường khác nhau.** Một máy có thể làm việc với dự án Java 17 và dự án Java 21 mà không phải liên tục thay đổi cài đặt toàn hệ thống.

**Cần dịch vụ phụ trợ cho kiểm thử.** Database, Redis hoặc message broker có thể được khởi động bằng Compose, tạo môi trường test gần với CI và dễ xóa sau khi hoàn tất.

**Lỗi chỉ xuất hiện trên CI.** Nếu nguyên nhân đến từ thư viện hệ thống, runtime hoặc công cụ build khác phiên bản, dùng cùng image cho local và CI giúp thu hẹp phạm vi khác biệt.

**Onboarding cần đơn giản.** Nhóm có thể cung cấp một lệnh để khởi tạo workspace thay vì yêu cầu người mới tự cài nhiều công cụ và chỉnh nhiều biến môi trường.

**Cần môi trường tạm thời và có thể tái tạo.** Container phù hợp với test integration, kiểm tra migration, build artifact hoặc thực hiện tác vụ cần trạng thái sạch.

Container không nhất thiết có lợi nếu dự án chỉ cần một runtime phổ biến, build tool đã có wrapper và không có phụ thuộc hệ thống phức tạp. Khi đó, wrapper cùng file cấu hình phiên bản có thể đủ đơn giản.

## 3. Khi nào không nên container hóa toàn bộ môi trường?

Container tạo thêm một lớp cần xây dựng, cập nhật, debug và bảo vệ. Nếu lợi ích không rõ, lớp này có thể làm chậm công việc.

Cân nhắc dùng môi trường native hoặc cách khác khi:

- Dự án nhỏ, phụ thuộc ít và có thể thiết lập ổn định bằng wrapper.
- Công việc cần tích hợp sâu với GUI, thiết bị USB, phần cứng hoặc driver đặc thù.
- Công cụ phụ thuộc mạnh vào kernel, module hệ điều hành hoặc tính năng chỉ có trên host.
- Repository lớn có lượng đọc/ghi file rất cao và bind mount qua máy ảo làm build chậm đáng kể.
- Nhóm không có khả năng duy trì image, vá lỗ hổng và cập nhật toolchain.
- Việc container hóa khiến debugger, IDE, chứng chỉ, VPN hoặc proxy của tổ chức trở nên phức tạp hơn lợi ích nhận được.

Một phương án trung gian thường hiệu quả: giữ IDE và editor trên host, chạy compiler, test và dịch vụ phụ trợ trong container. Cách này vẫn chuẩn hóa phần dễ gây khác biệt mà không bắt buộc mọi tương tác phải diễn ra bên trong container.

## 4. Phân biệt môi trường phát triển, môi trường kiểm thử và môi trường production

Một image có thể được dùng cho nhiều mục đích, nhưng mục tiêu và quyền hạn của từng môi trường khác nhau.

| Môi trường | Mục đích | Đặc điểm |
|---|---|---|
| Development container | Cung cấp toolchain và công cụ cho lập trình viên | Có thể mount source code, debugger và cache |
| Test container | Chạy unit/integration test trong môi trường tạm | Thường ngắn hạn, có dữ liệu test và dịch vụ phụ trợ |
| Build container | Tạo artifact từ revision xác định | Toolchain cố định, đầu ra được lưu hoặc chuyển sang bước tiếp theo |
| Runtime container | Chạy ứng dụng đã đóng gói | Chỉ chứa thành phần cần thiết khi ứng dụng hoạt động |

Không nên đưa toàn bộ công cụ phát triển, compiler, shell tiện ích và source code vào runtime image nếu ứng dụng không cần chúng khi chạy. Một Dockerfile nhiều stage có thể dùng image build chứa toolchain, sau đó chỉ sao chép artifact cần thiết sang image runtime nhỏ hơn.

Development container cũng không nên mặc định có credential production. Nó phục vụ công việc phát triển và kiểm thử, với quyền tương ứng cho môi trường đó.

## 5. Xác định môi trường bằng Dockerfile

Dockerfile mô tả các bước tạo image. Mỗi chỉ thị tạo một lớp hoặc cấu hình cho image. Dockerfile nên được quản lý trong version control để thay đổi môi trường có thể được review và truy vết như thay đổi mã nguồn.

Ví dụ Dockerfile đơn giản cho workspace Java:

```dockerfile
FROM eclipse-temurin:21-jdk

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bash \
       git \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 developer \
    && useradd --uid 10001 \
       --gid 10001 \
       --create-home \
       --shell /bin/bash developer

WORKDIR /workspace

USER developer

CMD ["bash"]
```

Đây là ví dụ khởi đầu. Image nền, gói hệ điều hành, phiên bản JDK và UID/GID cần được chọn theo yêu cầu thực tế. Nếu dùng image Debian hoặc Ubuntu, các lệnh apt phù hợp; image dựa trên Alpine hoặc distroless sẽ cần cách cài đặt khác.

Trong môi trường yêu cầu kiểm soát chặt, nên cố định image nền bằng digest sau khi đã xác minh nguồn và phiên bản. Tag như 21-jdk dễ đọc và thuận tiện cập nhật, nhưng tag có thể được nhà cung cấp cập nhật để trỏ tới image mới. Digest xác định chính xác nội dung image. Nhóm có thể dùng tag để diễn giải phiên bản và digest để khóa đầu vào.

Không nên dùng latest cho môi trường cần kết quả lặp lại. Khi nâng cấp image, hãy tạo thay đổi có review, chạy test và cập nhật tài liệu tương ứng.

## 6. Tổ chức Dockerfile để build hiệu quả

Thứ tự chỉ thị ảnh hưởng đến khả năng tái sử dụng cache của các lớp image. Các bước ít thay đổi nên được đặt trước các bước thường xuyên thay đổi.

Ví dụ, nếu cài gói hệ thống và công cụ trước khi copy source code, thay đổi một file Java không buộc Docker cài lại toàn bộ gói. Với dự án lớn, có thể tách dependency resolution khỏi bước copy source nếu build tool hỗ trợ.

Một số nguyên tắc:

- Chọn image nền chính thức và phiên bản phù hợp.
- Cài các gói cần thiết, tránh cài công cụ không sử dụng.
- Gộp các thao tác cài đặt và dọn cache trong cùng lớp khi phù hợp.
- Tách dependency và source code để cache có thể được tái sử dụng.
- Dùng multi-stage build nếu image build và image runtime có nhu cầu khác nhau.
- Chạy tiến trình bằng user không phải root khi có thể.
- Không đưa credential vào Dockerfile, build argument hoặc image layer.
- Dùng .dockerignore để loại bỏ dữ liệu không cần thiết khỏi build context.

Ví dụ .dockerignore:

```text
.git
.gradle
build
out
.idea
.vscode
.env
.env.*
*.log
```

Danh sách này cần điều chỉnh theo dự án. Nếu CI cần một file cấu hình được version hóa hoặc một thư mục build đầu vào, không được loại nó khỏi context một cách máy móc. Tệp secret và dữ liệu cá nhân không nên nằm trong build context.

Cache chỉ là tối ưu hiệu năng. Build phải vẫn có thể hoàn thành từ đầu vào chuẩn khi cache trống hoặc bị xóa. Không nên để kết quả đúng phụ thuộc vào một cache cục bộ chưa được quản lý.

## 7. Mount source code và quản lý workspace

Để lập trình viên chỉnh sửa mã trực tiếp bằng IDE trên host, workspace thường được mount vào container bằng bind mount. Container đọc và ghi cùng source tree mà người dùng đang làm việc.

Ví dụ với Docker Compose:

```yaml
services:
  workspace:
    build:
      context: .
      dockerfile: Dockerfile.dev
    working_dir: /workspace
    volumes:
      - .:/workspace
      - gradle-cache:/home/developer/.gradle
    command: ["sleep", "infinity"]

volumes:
  gradle-cache:
```

Trong ví dụ, source code được mount vào /workspace; cache Gradle được giữ trong named volume riêng để không phải tải dependency lại mỗi lần tạo container. Workspace có thể được chỉnh sửa trên host và công cụ trong container nhìn thấy thay đổi.

Cần hiểu vòng đời của từng loại volume:

- Bind mount liên kết thư mục host với đường dẫn trong container. Dữ liệu vẫn tồn tại trên host.
- Named volume do container runtime quản lý và có thể tồn tại sau khi container bị xóa.
- Writable layer của container thường mất khi container bị xóa; không nên lưu dữ liệu cần giữ lâu dài ở đó.

Không mount toàn bộ thư mục home của người dùng vào container nếu không cần thiết. Việc đó có thể đưa SSH key, cloud credential, cấu hình registry hoặc dữ liệu riêng vào môi trường có mức tin cậy khác. Chỉ mount những thư mục và tệp thật sự cần.

Đường dẫn mount nên ổn định và được tài liệu hóa. Với dự án Java, source có thể ở /workspace, còn cache Gradle ở home của user trong container. Điều này giúp task và báo cáo có vị trí nhất quán.

## 8. Xử lý quyền sở hữu file và khác biệt hệ điều hành

Một vấn đề phổ biến là file do container tạo ra có owner hoặc permission khác với người dùng host. Trên Linux, container chạy bằng UID/GID có thể tạo file thuộc về UID/GID đó trên bind mount. Nếu UID không khớp người dùng host, người phát triển có thể không sửa hoặc xóa file dễ dàng.

Có một số cách xử lý:

- Tạo user trong image có UID/GID phù hợp với host Linux.
- Dùng tính năng remote user hoặc UID mapping của môi trường Dev Container.
- Chọn thư mục đầu ra trong named volume nếu không cần chỉnh sửa trực tiếp trên host.
- Tránh chạy toàn bộ build bằng root chỉ để khắc phục permission.
- Dọn file với quyền phù hợp và kiểm tra trước khi thay đổi quyền đệ quy.

Trên Docker Desktop cho Windows hoặc macOS, lớp chia sẻ file có thể ánh xạ quyền khác với Linux native. Không nên giả định mọi hành vi permission giống nhau giữa các hệ điều hành. Hãy kiểm tra các thao tác thực tế của dự án, đặc biệt với script thực thi, symlink, line ending và file được sinh tự động.

Nếu build trên bind mount chậm, thử đặt source code hoặc cache trong filesystem Linux của môi trường máy ảo theo cách mà IDE hỗ trợ. So sánh thời gian build và trải nghiệm debug trước khi chọn cấu hình mặc định.

## 9. Sử dụng Docker Compose cho dịch vụ phụ trợ

Ứng dụng thường cần database, cache hoặc message broker để chạy integration test. Cài tất cả dịch vụ này trực tiếp trên máy lập trình viên tạo ra nhiều biến thể về phiên bản và cấu hình.

Compose cho phép mô tả nhiều container và mạng liên kết trong một file. Ví dụ sau khởi động PostgreSQL dùng riêng cho kiểm thử:

```yaml
services:
  database:
    image: postgres:16
    environment:
      POSTGRES_DB: app_test
      POSTGRES_USER: app
      POSTGRES_PASSWORD: local-test-only
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d app_test"]
      interval: 5s
      timeout: 3s
      retries: 10
```

Thông tin đăng nhập trong ví dụ chỉ dành cho môi trường test cục bộ và dữ liệu giả. Không dùng mật khẩu này cho môi trường dùng chung hoặc production. Nếu cần lưu dữ liệu giữa các lần chạy, có thể thêm named volume; nếu muốn mỗi lần kiểm thử bắt đầu từ dữ liệu sạch, hãy tạo môi trường tạm và xóa đúng volume test sau khi hoàn tất.

Các container trong cùng Compose network thường gọi nhau bằng tên service và cổng nội bộ. Ví dụ, ứng dụng trong container có thể kết nối tới hostname database và cổng 5432. Dùng localhost bên trong container ứng dụng sẽ trỏ về chính container đó, không phải container database.

Tách trạng thái health khỏi trạng thái process đang chạy. Container database có thể đã khởi động nhưng chưa sẵn sàng nhận kết nối. Health check và cơ chế chờ sẵn sàng giúp test tránh chạy quá sớm.

## 10. Dùng cùng môi trường cho local và CI

Khi image được quản lý cùng repository, CI có thể dùng chính image đó để chạy cùng task mà lập trình viên sử dụng.

Một luồng điển hình:

1. Checkout revision cần kiểm tra.
2. Lấy image theo tag hoặc digest đã được quy định.
3. Mount source hoặc copy source vào container.
4. Cấp biến môi trường không nhạy cảm và secret cần thiết qua cơ chế an toàn.
5. Chạy task chuẩn, ví dụ Gradle verify.
6. Thu thập test report và artifact.
7. Hủy container tạm sau khi hoàn tất.

Ví dụ lệnh minh họa trên Linux:

```bash
docker run --rm \
  --mount type=bind,source="$PWD",target=/workspace \
  --workdir /workspace \
  company/java-dev:21 \
  ./gradlew --no-daemon verify
```

Tên image là ví dụ. Trong thực tế, cần thay bằng image đã được xây dựng, kiểm tra và lưu trong registry của tổ chức. Nếu dùng PowerShell hoặc Windows path, cú pháp mount cần được viết theo shell và runtime tương ứng.

Có hai cách phổ biến để dùng image trong CI:

**Runner chạy job trong container.** Nền tảng CI cung cấp image cho toàn bộ job. Cách này phù hợp khi job chủ yếu cần chạy lệnh build và test bên trong image.

**Job điều khiển container bằng runtime.** Runner gọi Docker hoặc công cụ tương đương để tạo container, mount source và thu thập output. Cách này linh hoạt hơn nhưng runner cần quyền điều khiển runtime và cấu hình bảo mật phù hợp.

Không phải nền tảng CI nào cũng cho phép chạy container lồng nhau hoặc truy cập Docker daemon. Trước khi chọn cách triển khai, cần hiểu quyền của runner và cách nền tảng quản lý container.

## 11. Giữ cấu hình phát triển dễ dùng

Dev Container là một quy ước mô tả môi trường phát triển để IDE có thể mở workspace bên trong container. Một tệp cấu hình có thể chỉ rõ Dockerfile, thư mục workspace, user và các extension cần thiết.

Ví dụ cấu hình khái niệm:

```json
{
  "name": "Java development",
  "build": {
    "dockerfile": "Dockerfile.dev"
  },
  "workspaceFolder": "/workspace",
  "remoteUser": "developer"
}
```

Tên user phải tồn tại trong image. Cấu hình thực tế có thể thêm extension, port forwarding, mount hoặc lifecycle command tùy IDE. Không nên tự động cài quá nhiều extension hoặc chạy script không cần thiết mỗi lần mở workspace vì điều đó làm chậm onboarding.

Dev Container là cách cung cấp trải nghiệm phát triển nhất quán cho editor hỗ trợ chuẩn này. Nó không thay thế Dockerfile, task build hoặc pipeline. Những thành phần đó vẫn cần có thể sử dụng độc lập.

Tài liệu dự án nên có hướng dẫn tối thiểu: cài container runtime, mở workspace, chạy task chuẩn, khởi động dịch vụ phụ trợ và dừng môi trường. Người phát triển cần biết nơi lưu source, report và cache để không mất dữ liệu khi container bị tạo lại.

## 12. Bảo vệ container và host

Container giúp cô lập tiến trình nhưng không làm mã chưa tin cậy trở nên an toàn tuyệt đối. Container dùng chung kernel với host hoặc kernel của máy ảo bên dưới; cấu hình quyền quá rộng có thể làm tăng rủi ro cho máy chạy.

Các nguyên tắc cơ bản:

- Chạy bằng user không phải root khi có thể.
- Tránh dùng privileged mode nếu không có yêu cầu rõ ràng.
- Không mount Docker socket của host vào container phát triển hoặc container chạy mã PR chưa tin cậy.
- Không mount SSH key, cloud credential hoặc thư mục home đầy đủ nếu không cần.
- Giới hạn volume, network và quyền ghi theo đúng công việc.
- Dùng image từ nguồn đáng tin, quét lỗ hổng và cập nhật định kỳ.
- Không lưu secret trong image, build argument, layer hoặc log.
- Dùng runner tạm thời và môi trường cô lập cho mã đóng góp chưa tin cậy.
- Giới hạn CPU, memory và thời gian chạy khi cần tránh một tiến trình chiếm hết tài nguyên.

Docker socket thường cho phép điều khiển Docker daemon trên host. Nếu container có quyền truy cập socket đó, người chạy mã bên trong có thể tạo container khác hoặc truy cập tài nguyên host theo quyền của daemon. Vì vậy, mount socket không phải tiện ích vô hại.

Không đưa production secret vào development container chỉ để làm cho ứng dụng chạy giống production. Dùng dữ liệu giả, credential giới hạn quyền và môi trường test. Nếu cần kiểm thử tích hợp với hệ thống dùng chung, hãy cấp credential ngắn hạn và chỉ cho phép đúng hành động cần thiết.

Với mã từ pull request bên ngoài, cần xem cả Dockerfile, build script và dependency như mã có thể thực thi. Build image từ mã chưa tin cậy cũng có thể chạy lệnh tùy ý trong quá trình build. Không cấp secret hoặc quyền phát hành cho job đó.

## 13. Quản lý mạng và truy cập dịch vụ

Container có network namespace riêng và thường được kết nối vào bridge network hoặc mạng do nền tảng quản lý. Điều này giúp các dịch vụ trong môi trường test giao tiếp với nhau mà không phải cài lên host.

Cần xác định rõ:

- Cổng nào chỉ dùng nội bộ giữa các container.
- Cổng nào cần publish ra host để IDE hoặc công cụ bên ngoài truy cập.
- Hostname mà ứng dụng trong container sử dụng.
- Cách truy cập dịch vụ chạy trên host từ container theo runtime và hệ điều hành.
- Proxy, DNS, chứng chỉ CA và VPN cần thiết để tải dependency.

Không nên publish mọi cổng ra host nếu chỉ các container nội bộ cần giao tiếp. Khi publish cổng phát triển, nên giới hạn phạm vi truy cập nếu runtime hỗ trợ. Tránh dùng host network mode chỉ để giải quyết một vấn đề kết nối mà chưa hiểu nguyên nhân.

Môi trường doanh nghiệp có thể yêu cầu proxy hoặc chứng chỉ CA nội bộ. Các thiết lập đó nên được cung cấp theo cách có thể cấu hình và không đưa private key vào image. Nếu image cần CA certificate để truy cập registry hoặc dependency nội bộ, hãy quản lý certificate theo chính sách của tổ chức.

## 14. Cache dependency mà vẫn giữ khả năng tái tạo

Build trong container có thể tải dependency ở mỗi lần chạy nếu không có cache. Điều đó làm tăng thời gian và lưu lượng mạng. Có thể dùng named volume cho cache local và cơ chế cache do CI cung cấp.

Cache nên được phân biệt với đầu vào chuẩn:

- Dependency version và lockfile quyết định dependency cần dùng.
- Cache chỉ lưu dữ liệu tải hoặc kết quả trung gian để tăng tốc.
- Xóa cache không được làm build thay đổi logic hoặc không thể hoàn thành.
- Cache key nên gắn với hệ điều hành, toolchain hoặc lockfile khi các yếu tố đó ảnh hưởng đến nội dung cache.
- Không dùng cache chung cho các mức tin cậy khác nhau nếu có thể làm rò rỉ dữ liệu hoặc cho phép đầu ra không tin cậy tác động tới build đáng tin cậy.

Với Gradle, có thể mount thư mục .gradle vào named volume để tái sử dụng dependency và cache build. Trong CI, cache có thể được lưu và khôi phục bằng cơ chế của nền tảng. Khi kiểm tra tính tái tạo, nên có khả năng chạy build sạch không dùng cache để phát hiện phụ thuộc ngầm.

Không nên lưu source code hoặc artifact cần phát hành chỉ trong cache. Những dữ liệu đó phải được quản lý bằng version control hoặc artifact repository.

## 15. Tách image phát triển và image runtime

Image phát triển thường chứa JDK, compiler, shell, Git, debugger và công cụ phân tích. Ứng dụng production có thể chỉ cần JRE hoặc runtime tối thiểu. Dùng một image duy nhất cho cả hai mục đích có thể làm image production lớn hơn và mở rộng bề mặt tấn công.

Multi-stage build cho phép dùng một stage để build và stage khác để chạy ứng dụng:

```dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY . .
RUN ./gradlew --no-daemon clean build

FROM eclipse-temurin:21-jre AS runtime
WORKDIR /app
COPY --from=build /src/build/libs/app.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Đây là ví dụ khái niệm; đường dẫn JAR và cấu hình user phải khớp với dự án. Stage build có compiler và công cụ cần thiết; stage runtime chỉ nhận artifact và runtime cần để chạy. Nếu ứng dụng cần CA, font, timezone data hoặc thư viện native, cần bổ sung đúng các thành phần đó.

Không nên lấy development image làm runtime image chỉ vì nó đã có sẵn. Hãy xác định runtime cần những gì và kiểm tra image cuối cùng riêng.

## 16. Kiểm tra container environment

Dockerfile và cấu hình Compose cũng là mã nguồn, nên cần được review và kiểm tra. Một thay đổi image nền có thể thay đổi libc, chứng chỉ, runtime hoặc công cụ; thay đổi mount có thể làm lộ dữ liệu; thay đổi port có thể mở dịch vụ ra host.

Các kiểm tra hữu ích:

- Dockerfile build thành công từ checkout sạch.
- Image có đúng phiên bản runtime và công cụ đã khai báo.
- Container chạy bằng user dự kiến.
- Task chuẩn chạy được trong container.
- Volume chỉ mount đúng các thư mục cần thiết.
- Dịch vụ phụ trợ có health check và test chờ sẵn sàng.
- Secret không được copy vào image hoặc log.
- Container có thể bị xóa và tạo lại mà không mất dữ liệu cần giữ.
- Image runtime không chứa compiler hoặc công cụ phát triển không cần thiết.
- CI có thể thu thập test report và artifact từ container.

Có thể chạy lệnh kiểm tra trong container và ghi nhận phiên bản công cụ như một phần log. Điều này giúp giải thích khi image thay đổi. Khi cập nhật image, nên chạy lại bộ test quan trọng và kiểm tra tương thích với các hệ điều hành được hỗ trợ.

## 17. Quy trình áp dụng container cho một dự án

Một lộ trình thực tế có thể gồm:

1. **Ghi nhận khác biệt môi trường:** xác định lỗi hoặc chi phí onboarding đến từ runtime, thư viện hệ thống, dịch vụ phụ trợ hay công cụ.
2. **Chọn phạm vi container hóa:** chỉ đưa vào container những thành phần cần chuẩn hóa.
3. **Xác định toolchain:** chọn runtime, build tool, package và phiên bản phù hợp.
4. **Viết Dockerfile:** tạo image phát triển tối thiểu, dùng user không phải root và loại bỏ package không cần.
5. **Tổ chức workspace:** quyết định bind mount source, named volume cho cache và nơi lưu report.
6. **Bổ sung dịch vụ phụ trợ:** dùng Compose khi cần database hoặc broker cho kiểm thử.
7. **Kiểm tra local:** chạy task chuẩn, debug, kiểm tra permission và tốc độ file I/O.
8. **Tích hợp CI:** dùng cùng image hoặc cùng Dockerfile đã được khóa phiên bản để chạy task.
9. **Thiết lập bảo mật:** giới hạn quyền, volume, network, secret và runner.
10. **Tài liệu hóa:** hướng dẫn khởi động, lệnh kiểm tra, cập nhật image và dọn môi trường.
11. **Đo hiệu quả:** so sánh thời gian onboarding, độ ổn định và thời gian build trước/sau.

Không nên chuyển tất cả dịch vụ và thao tác vào container trong một lần. Bắt đầu từ phần gây sai khác lớn nhất, sau đó đánh giá xem lợi ích có bù được chi phí vận hành không.

## 18. Những lỗi thường gặp khi dùng container

| Cách làm chưa tốt | Hệ quả | Cách cải thiện |
|---|---|---|
| Dùng tag latest | Image có thể thay đổi mà không có review | Khóa tag phiên bản và digest khi cần |
| Chạy mọi tiến trình bằng root | Tăng tác động nếu container bị khai thác | Dùng user không phải root |
| Mount toàn bộ home directory | Credential và dữ liệu riêng bị lộ vào container | Chỉ mount thư mục cần thiết |
| Mount Docker socket tùy tiện | Container có thể điều khiển daemon host | Tránh mount socket, dùng runner/builder có kiểm soát |
| Lưu dữ liệu quan trọng trong writable layer | Mất dữ liệu khi xóa container | Dùng bind mount hoặc named volume có chủ đích |
| Dùng localhost để gọi container khác | Kết nối nhầm vào chính container | Dùng tên service trên network chung |
| Giả định process running là service ready | Test chạy trước khi database sẵn sàng | Dùng health check và cơ chế chờ |
| Chỉ chạy local trong container nhưng CI dùng image khác | Môi trường vẫn lệch nhau | Dùng cùng định nghĩa image và task |
| Đưa secret vào Dockerfile hoặc build arg | Secret có thể tồn tại trong layer/metadata | Dùng secret manager hoặc secret mount phù hợp |
| Image phát triển được dùng trực tiếp cho production | Image lớn và có nhiều công cụ không cần | Dùng multi-stage build và runtime image riêng |
| Cache là điều kiện bắt buộc | Build sạch thất bại hoặc cho kết quả khác | Xem cache là tối ưu, không phải nguồn chuẩn |
| Container hóa mọi thứ | Tăng độ phức tạp và giảm hiệu năng | Chọn đúng phần cần chuẩn hóa |

## 19. Đánh giá hiệu quả của môi trường container

Container chỉ tạo ra giá trị khi môi trường dễ tái tạo hơn và công việc ít phụ thuộc vào máy cá nhân hơn. Có thể theo dõi:

- Thời gian từ checkout đến khi chạy được bộ kiểm tra đầu tiên.
- Tỷ lệ lỗi do thiếu runtime, thư viện hoặc phiên bản công cụ.
- Tỷ lệ lỗi CI có thể tái hiện trong môi trường local chuẩn.
- Thời gian build khi cache nóng và khi cache lạnh.
- Dung lượng image và thời gian tải image.
- Số lần phải xử lý lỗi permission hoặc mount.
- Tần suất cập nhật image và thời gian xử lý lỗ hổng.
- Mức độ dễ dàng tạo lại môi trường sau khi container bị xóa.

Nếu image ngày càng lớn, khởi động chậm hoặc cần nhiều bước đặc biệt để debugger hoạt động, hãy xem lại phạm vi container hóa. Nếu cùng image chạy ổn định trên local và CI, onboarding nhanh hơn và lỗi môi trường giảm, container đang tạo ra giá trị rõ ràng.

## 20. Checklist lựa chọn và vận hành

Trước khi chuẩn hóa container làm môi trường công việc, hãy rà soát:

- [ ] Có vấn đề môi trường cụ thể mà container giải quyết.
- [ ] Image được mô tả bằng Dockerfile và quản lý trong version control.
- [ ] Image nền có nguồn tin cậy và phiên bản rõ ràng.
- [ ] Toolchain và dependency được kiểm soát.
- [ ] Container chạy bằng user không phải root khi có thể.
- [ ] Source, cache, report và dữ liệu test có vị trí lưu trữ rõ ràng.
- [ ] Không mount credential hoặc thư mục host rộng hơn nhu cầu.
- [ ] Không cấp privileged mode hoặc Docker socket nếu không có lý do được kiểm soát.
- [ ] Mạng và cổng được giới hạn theo mục đích.
- [ ] Dịch vụ phụ trợ có health check.
- [ ] Local và CI dùng cùng task và môi trường tương đương.
- [ ] Build vẫn hoạt động khi cache trống.
- [ ] Có thể xóa và tạo lại container mà không mất dữ liệu cần giữ.
- [ ] Image được cập nhật và kiểm tra định kỳ.
- [ ] Có tài liệu khởi động, sử dụng, cập nhật và dọn môi trường.

## Kết luận

Container là công cụ hữu ích để đóng gói toolchain, thư viện hệ thống và dịch vụ phụ trợ thành môi trường có thể khởi tạo lại. Khi local và CI dùng cùng image hoặc cùng định nghĩa môi trường, nhóm có thể giảm khác biệt, tái hiện lỗi dễ hơn và đơn giản hóa onboarding.

Hiệu quả phụ thuộc vào phạm vi sử dụng và cách vận hành. Image cần được quản lý bằng mã, phiên bản cần được kiểm soát, source và cache cần có vòng đời rõ, container cần chạy với quyền tối thiểu và secret cần được cấp an toàn. Chỉ container hóa những phần thực sự cần chuẩn hóa sẽ giúp nhóm giữ được sự cân bằng giữa tính nhất quán, hiệu năng và độ đơn giản.

