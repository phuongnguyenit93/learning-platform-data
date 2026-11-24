# Đóng gói hàm bằng source package hoặc container image

Một hàm serverless không chỉ gồm vài dòng mã nguồn. Để nền tảng có thể khởi tạo hàm và xử lý sự kiện, mã nguồn phải đi cùng runtime, thư viện phụ thuộc, cấu hình handler và những tài nguyên cần thiết. Tập hợp đó được đóng gói thành một artifact triển khai.

Hai cách đóng gói phổ biến là **source package** và **container image**. Source package thường chứa mã nguồn cùng dependency theo định dạng mà nền tảng hỗ trợ, chẳng hạn ZIP hoặc gói ngôn ngữ. Container image đóng gói ứng dụng trong một image theo chuẩn OCI, gồm filesystem, runtime và dependency. Mỗi cách có quy trình build, giới hạn kích thước, cách kiểm thử và đặc tính khởi động khác nhau.

Bài học thuộc module **CLOUD_CORE_SERVICES_COMPUTE**, chương **Mô hình hàm serverless**. Nội dung giúp chọn hình thức đóng gói phù hợp, tổ chức handler và dependency, tạo artifact tái lập, kiểm tra tương thích kiến trúc, tối ưu thời gian khởi động, triển khai an toàn và bảo vệ chuỗi cung ứng phần mềm.

## 1. Artifact triển khai của một hàm serverless

Khi một sự kiện đến, nền tảng serverless cần biết mã thực thi nằm ở đâu, runtime nào được sử dụng, handler nào nhận sự kiện, thư viện nào phải được nạp, cấu hình nào được áp dụng và cách khởi động ứng dụng.

Artifact triển khai là phần nội dung được build và phát hành để nền tảng thực thi. Artifact có thể là source package hoặc container image. Một số nền tảng nhận source code rồi tự build thành artifact nội bộ; một số cho phép nhà phát triển tự build image và đưa image lên registry.

### 1.1. Những thành phần thường có trong artifact

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Handler code | Điểm vào xử lý sự kiện | Hàm xử lý HTTP request hoặc queue message |
| Runtime | Môi trường thực thi ngôn ngữ | Python, Node.js, Java, .NET |
| Dependencies | Thư viện ứng dụng cần | SDK, parser, framework |
| Native libraries | Thư viện biên dịch cho hệ điều hành/CPU | OpenSSL, image codec, database client |
| Assets | File ứng dụng cần khi chạy | Template, schema, model nhỏ |
| Entrypoint/handler configuration | Xác định cách gọi ứng dụng | Module và tên hàm, executable hoặc command |
| Metadata | Thông tin build và phát hành | Version, commit, checksum, SBOM |

Không phải nền tảng nào cũng yêu cầu nhà phát triển đóng gói runtime. Với managed runtime, nhà cung cấp cung cấp sẵn runtime tương thích; source package chỉ cần chứa mã và dependency được yêu cầu. Với custom runtime hoặc container image, nhóm phát triển chịu trách nhiệm nhiều hơn về môi trường thực thi.

### 1.2. Source package và container image trong luồng triển khai

~~~mermaid
flowchart TD
    S["Source code + dependency manifest"] --> B["Build / Resolve dependencies"]
    B --> P["Source package"]
    B --> I["Container image"]
    P --> V["Validate package layout and handler"]
    I --> R["Build OCI layers and image metadata"]
    V --> A["Publish artifact"]
    R --> A
    A --> D["Deploy function configuration"]
    D --> T["Invoke with test event"]
    T --> M["Monitor errors, latency and cold start"]
~~~

Build và deploy là hai bước có trách nhiệm khác nhau. Build tạo artifact bất biến; deploy gắn artifact đó với cấu hình hàm như handler, memory, timeout, environment, trigger và quyền thực thi. Tách hai bước giúp cùng một artifact được promote qua test, staging và production mà không phải build lại khác nhau ở mỗi môi trường.

## 2. Source package là gì?

Source package là gói chứa mã nguồn và những file cần thiết để nền tảng nạp hàm. Các định dạng thường gặp gồm ZIP chứa source code và thư viện đã cài, JAR cho ứng dụng Java, gói deployment do công cụ build của nền tảng tạo hoặc gói source được nền tảng build bằng buildpack.

Source package thường phù hợp khi nền tảng cung cấp managed runtime tương thích và dependency có thể được đóng gói theo quy ước của runtime đó.

### 2.1. Cấu trúc package

Ví dụ một source package Python:

~~~text
function-package/
  app.py
  handlers/
    __init__.py
    orders.py
  common/
    __init__.py
    validation.py
  requests/
    ...
  certifi/
    ...
~~~

File app.py có thể định nghĩa handler:

~~~python
import json

def handle_order(event, context):
    order_id = event.get("order_id")
    if not order_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "missing order_id"}),
        }

    return {
        "statusCode": 200,
        "body": json.dumps({"accepted": True, "order_id": order_id}),
    }
~~~

Tên module và hàm handler phải khớp cấu hình của nền tảng. Một nền tảng có thể yêu cầu chuỗi chỉ tới module và function; nền tảng khác dùng convention hoặc manifest riêng. Không mặc định mọi provider đều dùng cùng cú pháp handler.

### 2.2. Đưa dependency vào package

Source package cần chứa dependency mà runtime không cung cấp sẵn. Có thể dùng package manager để cài thư viện vào thư mục build:

~~~bash
python -m pip install --requirement requirements.txt --target build/package
Copy-Item app.py build/package/app.py
Compress-Archive -Path build/package/* -DestinationPath function.zip
~~~

Đoạn lệnh trên minh họa quy trình trên Windows PowerShell. Trong CI Linux, có thể dùng công cụ ZIP tương ứng. Cần kiểm tra nội dung archive sau khi tạo để bảo đảm file handler và thư viện nằm đúng cấp thư mục mà runtime tìm kiếm.

Không đưa toàn bộ môi trường phát triển vào package. Virtual environment, test data, cache pip, Git metadata, IDE config và file build không cần thiết sẽ làm artifact lớn và tăng thời gian tải/nạp.

### 2.3. Dependency manifest và lock file

Manifest khai báo thư viện trực tiếp mà ứng dụng cần. Lock file ghi lại phiên bản đã resolve cùng dependency bắc cầu để build có thể tái lập.

Ví dụ requirements có pin phiên bản:

~~~text
requests==2.32.3
pydantic==2.9.2
~~~

Với hệ sinh thái khác, dùng package lock tương ứng như package-lock.json, pnpm-lock.yaml, poetry.lock, uv.lock, packages.lock.json hoặc file dependency lock của build tool Java.

Chỉ pin thư viện trực tiếp có thể chưa đủ nếu dependency bắc cầu thay đổi. Hãy tạo và kiểm tra lock file, cập nhật có chủ đích và ghi lại phiên bản runtime/toolchain trong pipeline.

## 3. Container image là gì?

Container image là template bất biến để tạo container. Image thường bao gồm filesystem layers, runtime hoặc base operating system userspace, ứng dụng và dependency, native libraries cùng metadata về entrypoint, command, environment mặc định và user.

Image theo chuẩn OCI có thể được lưu trong container registry và được tham chiếu bằng tag hoặc digest. Nền tảng serverless hỗ trợ container image sẽ lấy image từ registry rồi khởi tạo môi trường thực thi theo hợp đồng riêng của nền tảng.

Container image phù hợp khi cần kiểm soát runtime, native dependency, hệ điều hành userspace hoặc muốn dùng chung cách đóng gói với môi trường container khác.

### 3.1. Dockerfile cơ bản

~~~dockerfile
FROM python:3.12-slim

WORKDIR /function

COPY requirements.txt .
RUN pip install --no-cache-dir --requirement requirements.txt

COPY app.py .
COPY common/ ./common/

# Lệnh thực tế phải tuân theo runtime contract của nền tảng serverless.
CMD ["python", "-m", "app"]
~~~

Dockerfile trên chỉ minh họa cách đóng gói ứng dụng Python thành image. Một nền tảng function container có thể yêu cầu base image riêng, runtime interface client, bootstrap executable hoặc HTTP server theo giao thức của nó. Không thể mặc định CMD tùy ý sẽ được nền tảng gọi đúng như một web container thông thường.

### 3.2. Base image

Base image quyết định phần lớn môi trường userspace ban đầu. Hãy chọn image tương thích runtime và kiến trúc CPU của nền tảng, có nguồn phát hành và chính sách cập nhật rõ ràng, chứa ít thành phần không cần thiết, được vá bảo mật định kỳ và có thể pin bằng digest để build tái lập.

Image slim hoặc distroless có thể giảm kích thước và bề mặt tấn công, nhưng cần xác minh có đủ CA certificates, timezone data, shell/tooling hoặc thư viện runtime mà ứng dụng yêu cầu. Kiểm tra bằng test trên image cuối trước khi loại bỏ thành phần.

## 4. So sánh source package và container image

| Tiêu chí | Source package | Container image |
|---|---|---|
| Runtime | Thường dùng managed runtime hoặc runtime do nền tảng cung cấp | Có thể đóng gói runtime/userspace theo yêu cầu nền tảng |
| Thành phần kiểm soát | Source, dependency và file hỗ trợ | Filesystem, runtime, dependency, native library và metadata |
| Build | Package manager, ZIP/JAR hoặc build service | Container build engine tạo OCI image |
| Độ phức tạp | Thường thấp hơn nếu runtime chuẩn | Cao hơn do quản lý base image, layers và registry |
| Native dependency | Phải build đúng môi trường runtime/ABI/CPU | Dễ kiểm soát userspace hơn nhưng vẫn phải đúng OS/ABI/CPU |
| Kích thước | Thường nhỏ nếu dependency gọn | Có thể lớn do base image và layers |
| Khởi động | Có thể nhanh khi package nhỏ và runtime có sẵn | Phụ thuộc kích thước image, cache, runtime bootstrap và nền tảng |
| Tính nhất quán | Phụ thuộc managed runtime và build environment | Có thể đóng gói môi trường nhất quán hơn |
| Tái sử dụng | Dễ dùng trong hệ sinh thái function runtime tương ứng | Có thể dùng lại trong môi trường OCI tương thích |
| Phù hợp | Hàm nhỏ, runtime chuẩn, dependency thuần ngôn ngữ | Native dependency phức tạp, runtime tùy chỉnh, cần kiểm soát userspace |

Không có lựa chọn luôn tốt hơn. Source package thường giảm gánh nặng vận hành khi managed runtime đáp ứng nhu cầu. Container image tăng quyền kiểm soát nhưng nhóm phát triển phải chịu trách nhiệm nhiều hơn về cập nhật base image, scan lỗ hổng, tương thích runtime và registry.

## 5. Cách chọn hình thức đóng gói

Hãy chọn theo yêu cầu của workload:

| Câu hỏi | Ưu tiên source package khi... | Ưu tiên container image khi... |
|---|---|---|
| Runtime | Runtime chuẩn của provider đáp ứng | Cần runtime hoặc userspace tùy chỉnh |
| Dependency | Thư viện thuần ngôn ngữ, dễ cài | Có native library hoặc OS package đặc thù |
| Kiểm soát môi trường | Chấp nhận môi trường managed | Cần pin userspace và cấu hình image |
| Kích thước | Artifact có thể giữ gọn | Có thể tối ưu layers và chấp nhận image lớn hơn |
| Công cụ build | Package manager là đủ | Đã có Docker/OCI build pipeline |
| Vận hành | Muốn giảm trách nhiệm quản lý OS image | Có quy trình vá, scan và phát hành image |
| Khả năng tái sử dụng | Chủ yếu trong một function platform | Cần cùng artifact cho nhiều môi trường OCI |

Một quy tắc thực tế: bắt đầu từ source package nếu nền tảng có runtime phù hợp và dependency đơn giản. Chuyển sang container image khi có lý do cụ thể như native library khó đóng gói, runtime tùy chỉnh, yêu cầu userspace hoặc quy trình build chung với container platform.

### 5.1. Không chọn container image chỉ vì ứng dụng đang có Dockerfile

Một Dockerfile dành cho web service không tự động tương thích với function platform. Function platform có thể yêu cầu runtime interface hoặc adapter nhận invocation, handler qua biến môi trường hoặc metadata, quy ước request/response riêng, cổng nội bộ, bootstrap và health check riêng, hoặc giới hạn filesystem và thời gian khởi tạo.

Trước khi chọn image, hãy xác minh image contract của nền tảng: entrypoint, command, handler, port, protocol, signal và cách truyền event.

## 6. Handler và runtime contract

Handler là điểm vào mà nền tảng gọi khi một invocation đến. Runtime contract quy định cách nền tảng chuyển event, context, deadline và kết quả tới ứng dụng.

Một handler có thể nhận event payload, context chứa request ID/deadline, environment variables và runtime context tùy framework.

### 6.1. Tách logic nghiệp vụ khỏi adapter

~~~python
def handle_order(event, context):
    command = parse_order_event(event)
    result = order_service.accept(command)
    return format_response(result)
~~~

order_service không cần biết event đến từ API gateway, queue hay scheduler. Adapter chịu trách nhiệm parse payload, xác thực cấu trúc và định dạng kết quả theo trigger.

Lợi ích:

- Unit test logic nghiệp vụ mà không cần runtime cloud.
- Có thể thay trigger mà ít sửa code.
- Dễ chạy cùng logic trong local test và function runtime.
- Giảm phụ thuộc vào SDK hoặc context riêng của provider.

### 6.2. Khởi tạo ngoài handler

Một số nền tảng giữ execution environment để tái sử dụng giữa nhiều invocation. Có thể khởi tạo client, connection pool hoặc schema cache ở scope module để giảm chi phí lặp lại.

Tuy nhiên, không giả định cùng một instance luôn nhận invocation tiếp theo; không lưu dữ liệu nghiệp vụ chỉ trong global memory; kiểm tra kết nối có thể hết hạn; không chia sẻ mutable state giữa invocation nếu chưa có đồng bộ; dùng lazy initialization nếu dependency chỉ cần cho một số nhánh.

## 7. Build source package đúng runtime

Source package phải tương thích với runtime mà nền tảng sẽ dùng. Điều này bao gồm phiên bản ngôn ngữ, hệ điều hành, CPU architecture, ABI và native library.

### 7.1. Build dependency trong môi trường tương thích

Một dependency Python có native extension được build cho Windows x86-64 sẽ không chạy trong Linux ARM64 chỉ vì file ZIP được upload thành công. Tương tự, Java JNI library hoặc Node.js native addon cũng phụ thuộc hệ điều hành và kiến trúc.

Hãy build dependency trong build container tương thích runtime, CI runner có OS/architecture phù hợp, build service do provider hỗ trợ hoặc cross-compilation toolchain đã được kiểm thử.

Đối với package chỉ có mã thuần ngôn ngữ, việc build thường đơn giản hơn nhưng vẫn cần kiểm tra phiên bản runtime và dependency.

### 7.2. Ví dụ build Python package trong Linux container

~~~bash
docker run --rm --platform linux/amd64 -v "$PWD:/workspace" -w /workspace python:3.12-slim sh -c "python -m pip install -r requirements.txt -t build/package"
~~~

Ví dụ minh họa build dependency cho Linux AMD64. Hãy thay platform và runtime image theo môi trường đích. Không dùng kết quả build AMD64 cho ARM64 nếu dependency có binary native.

### 7.3. Kiểm tra cấu trúc archive

~~~bash
unzip -l function.zip
~~~

Kiểm tra handler có ở đúng vị trí không, dependency có nằm trong thư mục runtime tìm kiếm không, có lồng thêm một cấp folder ngoài ý muốn không, có file test/cache/credential bị đóng gói không, có file native đúng architecture không và có file cấu hình/certificate cần thiết không.

Archive tạo ra từ thư mục cha thay vì nội dung thư mục package có thể khiến runtime không tìm thấy module/handler dù file thực tế vẫn nằm trong ZIP.

## 8. Dependency và native library

Dependency có thể chia thành dependency thuần ngôn ngữ, dependency có native extension, OS package và runtime tool. Source package thường yêu cầu nhóm phát triển tự bảo đảm dependency native phù hợp với môi trường managed runtime. Container image cho phép đóng gói thêm OS package, nhưng không loại bỏ yêu cầu tương thích kernel interface, architecture và runtime contract.

### 8.1. Tránh phụ thuộc thư viện trên máy build

Một lỗi phổ biến là package chạy được trên laptop nhưng thiếu thư viện hệ thống trên serverless runtime. Máy build có thể đã cài sẵn shared library mà artifact không mang theo.

~~~bash
ldd path/to/native-extension.so
~~~

Lệnh ldd là công cụ Linux và chỉ phù hợp với binary tương thích. Kiểm tra output để tìm shared library bị thiếu; với binary không tin cậy, dùng công cụ phân tích tĩnh phù hợp thay vì thực thi tùy tiện.

### 8.2. CA certificates và timezone

Ứng dụng gọi HTTPS có thể cần CA bundle. Xử lý ngày giờ có thể cần timezone database. Base image tối giản đôi khi bỏ các thành phần này để giảm dung lượng.

Nếu request HTTPS thất bại với lỗi xác minh certificate hoặc logic thời gian sai, kiểm tra CA bundle, timezone data và cấu hình runtime trước khi kết luận endpoint từ xa có vấn đề.

## 9. Build container image có thể tái lập

Một image tốt cần được build từ source và dependency đã xác định, có thể truy ngược tới commit, được kiểm thử và phát hành bằng digest. Không nên build image trực tiếp trên máy cá nhân rồi đẩy lên production mà không có quy trình kiểm tra.

### 9.1. Multi-stage build

Multi-stage build tách môi trường biên dịch khỏi image runtime. Các compiler, header, package manager cache và công cụ build không cần có trong image cuối.

~~~dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --requirement requirements.txt --target /install

FROM python:3.12-slim AS runtime
WORKDIR /function
COPY --from=builder /install /opt/python
ENV PYTHONPATH=/opt/python
COPY app.py .
COPY common/ ./common/
CMD ["python", "-m", "app"]
~~~

Ví dụ này cho thấy dependency được cài ở stage builder rồi chỉ phần cần thiết được sao chép sang runtime stage. Base image của hai stage nên tương thích về ABI và native libraries. Với nền tảng function container, cần thay command bằng entrypoint/runtime interface mà nền tảng yêu cầu.

### 9.2. Pin base image

Tag như python:3.12-slim có thể trỏ tới nội dung khác nhau theo thời gian khi image được cập nhật. Pin bằng digest giúp build sử dụng đúng nội dung base image đã được phê duyệt.

~~~dockerfile
FROM python:3.12-slim@sha256:REPLACE_WITH_APPROVED_DIGEST
~~~

Digest ở đây là placeholder. Pipeline phải lấy digest thực từ registry đáng tin cậy, xác minh và cập nhật có chủ đích. Pin digest giúp tái lập nhưng không tự cập nhật bản vá; cần quy trình định kỳ phát hiện base image mới và rebuild.

### 9.3. Build context và .dockerignore

Build context là tập file được gửi tới container builder. Một file .dockerignore giúp loại các nội dung không cần thiết:

~~~text
.git
.venv
__pycache__
.pytest_cache
tests
coverage
.env
*.pem
*.key
~~~

Không đưa credential, file môi trường cá nhân, private key hoặc dữ liệu thử nghiệm vào build context. Việc bỏ qua một file trong image không xóa dữ liệu nhạy cảm đã từng được commit vào Git hoặc lưu trong build logs; hãy xử lý secret ở nguồn và lịch sử nếu đã bị lộ.

## 10. Kiến trúc CPU và ABI

Function runtime có thể chạy trên các kiến trúc như x86-64/AMD64 hoặc ARM64. Artifact phải tương thích với kiến trúc được cấu hình cho hàm.

Các điểm cần kiểm tra:

- Architecture của function configuration.
- Architecture của binary trong source package.
- Architecture và manifest của container image.
- ABI và libc mà native dependency yêu cầu.
- Runtime version và compiler target.
- Các thư viện native được nạp lúc khởi động.

### 10.1. Container image đa kiến trúc

OCI image index/manifest list có thể tham chiếu nhiều image manifest cho các kiến trúc khác nhau. Registry và nền tảng cần hỗ trợ image đa kiến trúc; không phải function platform nào cũng chấp nhận mọi manifest list.

~~~bash
docker buildx build --platform linux/amd64,linux/arm64 --tag registry.example.com/orders-function:1.4.0 --push .
~~~

Lệnh này minh họa Buildx. Cần kiểm tra builder hỗ trợ target platform, dependency native có build được cho cả hai kiến trúc và nền tảng serverless hỗ trợ manifest đó. Nếu provider yêu cầu một architecture cụ thể, phát hành image đúng target thay vì dựa vào lựa chọn mặc định.

### 10.2. Kiểm tra binary

~~~bash
file path/to/native-library.so
readelf -h path/to/native-library.so
~~~

Kết quả giúp xác nhận định dạng ELF và machine architecture. Kiểm tra thêm dynamic linker và shared library cần thiết; binary đúng kiến trúc vẫn có thể không chạy nếu ABI hoặc thư viện hệ thống không tương thích.

## 11. Kích thước artifact và cold start

Cold start là khoảng thời gian cần để nền tảng chuẩn bị execution environment trước khi hàm xử lý invocation. Một phần thời gian có thể gồm tải artifact, giải nén hoặc mount package, khởi tạo runtime, import dependency, tạo client và kết nối tới dịch vụ bên ngoài.

Kích thước package/image có thể ảnh hưởng thời gian tải và khởi tạo, nhưng không phải yếu tố duy nhất. Runtime, số lượng dependency, native initialization, network, registry cache và cơ chế nền tảng đều có ảnh hưởng.

### 11.1. Tối ưu source package

- Chỉ đóng gói dependency thực sự được sử dụng.
- Loại test, cache, bytecode không cần thiết và tài liệu phát triển.
- Tránh copy toàn bộ virtual environment.
- Tách dependency dùng chung theo cơ chế layer nếu nền tảng hỗ trợ.
- Dùng lock file và cài dependency ở build stage.
- Tránh import nặng ở module scope nếu chỉ một nhánh cần dùng.
- Kiểm tra kích thước artifact và thời gian nạp sau mỗi thay đổi.

### 11.2. Tối ưu container image

- Dùng base image tối giản nhưng vẫn đủ runtime dependency.
- Áp dụng multi-stage build.
- Gom các bước cài package để giảm layer thừa.
- Xóa package cache và file build khỏi final stage.
- Không copy source tree, test data hoặc credential không cần thiết.
- Chọn đúng architecture để tránh image chứa binary thừa.
- Dùng registry gần với môi trường triển khai nếu nền tảng hỗ trợ lựa chọn vị trí.

### 11.3. Đo thay vì đoán

Theo dõi riêng kích thước source package hoặc compressed image, thời gian publish và tải artifact, runtime bootstrap, import module, khởi tạo dependency, cold-start latency p50/p95/p99, warm invocation latency và tỷ lệ cold start theo traffic pattern.

Không hy sinh bảo mật hoặc tính đúng đắn chỉ để giảm vài megabyte. Loại bỏ native library cần thiết có thể khiến hàm khởi động thất bại; giảm log quá mức có thể làm mất khả năng điều tra.

## 12. Cấu hình runtime và môi trường

Artifact nên chứa mã và dependency; cấu hình thay đổi theo môi trường thường được cung cấp qua function configuration hoặc environment variables.

Các cấu hình thường gặp:

- Handler hoặc runtime entrypoint.
- Timeout và memory.
- CPU/architecture nếu nền tảng cho phép chọn.
- Environment variables.
- Network/VPC attachment.
- Execution role hoặc service identity.
- Trigger và concurrency.
- Temporary storage.

Không hard-code endpoint, account identifier, password hoặc token trong source package hay image. Cùng một artifact nên được triển khai qua các môi trường bằng cấu hình bên ngoài.

### 12.1. Environment variables

Environment variables phù hợp với cấu hình không bí mật như tên môi trường, feature flag hoặc endpoint. Với secret, dùng secret manager hoặc cơ chế quản lý bí mật của nền tảng và cấp quyền đọc tối thiểu cho execution identity.

Không in toàn bộ environment vào log khi debug. Một số biến có thể chứa credential hoặc thông tin nội bộ.

### 12.2. Execution identity

Quyền truy cập tài nguyên nên được cấp cho identity mà function runtime sử dụng. Artifact không nên mang theo access key tĩnh. Dùng role/managed identity/service account và quyền tối thiểu cho queue, storage, database hoặc secret manager cần thiết.

## 13. Kiểm thử artifact trước khi deploy

Unit test source code chưa đủ để chứng minh artifact triển khai hoạt động. Một package có thể thiếu file, sai handler hoặc dependency; image có thể chạy trên máy phát triển nhưng không tương thích runtime contract.

Nên kiểm thử theo nhiều lớp:

1. Unit test: kiểm tra logic nghiệp vụ.
2. Handler test: kiểm tra event/context và response format.
3. Package inspection: xác minh file, dependency, kích thước và metadata.
4. Runtime compatibility test: chạy artifact với runtime/architecture tương thích.
5. Invocation test: gọi bằng event đại diện cho trigger thực tế.
6. Failure test: dependency timeout, payload lỗi, retry và timeout.
7. Performance test: cold start, warm latency, memory và concurrency.
8. Security scan: kiểm tra dependency, base image và secret.

### 13.1. Kiểm tra ZIP

~~~bash
unzip -t function.zip
unzip -l function.zip
~~~

Lệnh đầu xác minh archive có thể đọc; lệnh sau liệt kê nội dung. Sau đó cần chạy một smoke test trong runtime tương thích để xác minh handler thực sự được nạp.

### 13.2. Kiểm tra container image

~~~bash
docker image inspect registry.example.com/orders-function:1.4.0
docker run --rm registry.example.com/orders-function:1.4.0
~~~

Lệnh run chỉ phù hợp nếu image có chế độ local execution hoặc command mặc định có thể chạy độc lập. Với function image, có thể cần runtime emulator hoặc local invocation harness của provider để gửi event đúng giao thức.

### 13.3. Test event đại diện

Test event cần bao gồm payload hợp lệ tối thiểu, payload lớn nhưng trong giới hạn, thiếu trường bắt buộc, giá trị không đúng kiểu, ký tự Unicode và dữ liệu biên, dependency timeout hoặc trả lỗi, request retry hoặc message được giao lại.

Đối với queue trigger, kiểm tra semantics acknowledgement và batch failure. Đối với HTTP trigger, kiểm tra status code, header, body và timeout. Đối với scheduled trigger, kiểm tra timezone và idempotency.

## 14. Quy trình CI/CD cho function artifact

Một pipeline đáng tin cậy tạo artifact một lần, kiểm tra, lưu trữ và promote cùng artifact qua môi trường.

~~~mermaid
flowchart LR
    C["Commit"] --> L["Lint + Unit tests"]
    L --> B["Build package/image"]
    B --> V["Inspect + Compatibility tests"]
    V --> S["Security scan + SBOM"]
    S --> P["Publish immutable artifact"]
    P --> D["Deploy to test"]
    D --> I["Invocation / integration tests"]
    I --> A["Approval / promotion"]
    A --> R["Deploy same digest/version"]
    R --> O["Observe and rollback if needed"]
~~~

Các bước chính:

- Checkout đúng commit và kiểm tra dependency manifest.
- Cài toolchain/runtime version đã xác định.
- Chạy lint, unit test và test bảo mật mã nguồn.
- Build source package hoặc OCI image.
- Kiểm tra cấu trúc, kích thước và architecture.
- Tạo checksum, SBOM và scan dependency/image.
- Publish artifact bất biến.
- Deploy test/staging và gọi bằng event đại diện.
- Promote cùng artifact sang production.
- Theo dõi lỗi, latency và rollback theo version đã biết.

### 14.1. Không rebuild khác nhau giữa staging và production

Nếu staging và production dùng artifact được build từ hai lần khác nhau, dependency hoặc base image có thể đã thay đổi. Khi có sự cố, khó chứng minh hai môi trường đang chạy cùng nội dung.

Hãy publish artifact với version hoặc digest bất biến rồi tham chiếu đúng artifact đó trong từng môi trường. Cấu hình runtime có thể khác, nhưng binary/package/image nên giống nhau.

### 14.2. Version và digest

Tag dễ đọc như 1.4.0 thuận tiện cho người vận hành nhưng có thể bị ghi đè nếu registry cho phép. Digest xác định nội dung image chính xác. Với source package, lưu checksum và version artifact trong hệ thống phát hành.

Deployment record nên ghi source commit, build ID và builder identity, runtime/toolchain version, dependency lock file hash, package checksum hoặc image digest, SBOM và kết quả scan, cùng function configuration version.

## 15. Bảo mật chuỗi cung ứng artifact

Source package và container image đều có thể mang theo dependency độc hại, thư viện có lỗ hổng hoặc secret bị đóng gói nhầm. Bảo mật cần áp dụng từ lúc resolve dependency tới lúc deploy.

### 15.1. Dependency hygiene

- Dùng package registry đáng tin cậy.
- Pin phiên bản và review cập nhật.
- Hạn chế dependency không cần thiết.
- Theo dõi lỗ hổng và license.
- Không cài package từ URL không xác minh.
- Khóa phiên bản compiler, runtime và build tool.

### 15.2. SBOM

Software Bill of Materials (SBOM) mô tả thành phần phần mềm trong artifact. SBOM hỗ trợ inventory dependency, truy vấn ảnh hưởng khi có lỗ hổng và kiểm tra license.

SBOM cần được gắn với đúng artifact version/digest. Nếu build lại hoặc thay dependency, phải tạo SBOM mới tương ứng.

### 15.3. Image scanning và signing

Với container image, scan base image và package ở các layer. Image cuối có thể còn file hoặc package từ stage trước nếu multi-stage copy không được thiết kế đúng.

Có thể ký image hoặc artifact và xác minh chữ ký trước deploy. Chữ ký chỉ hữu ích khi trust policy, identity người ký và quy trình xác minh được cấu hình đúng.

### 15.4. Secret scanning

Kiểm tra source package, image layers và build context để phát hiện private key, token, password hoặc file môi trường. Xóa file ở layer sau không nhất thiết xóa nội dung đã được lưu trong layer trước của image; tránh đưa secret vào build context ngay từ đầu.

## 16. Registry và quyền truy cập artifact

Container image thường được lưu trong registry. Source package có thể lưu trong artifact repository hoặc dịch vụ quản lý code/deployment package của provider.

Các yêu cầu vận hành:

- Registry/repository có authentication và authorization.
- Function deployment identity chỉ có quyền pull artifact cần thiết.
- CI identity có quyền push vào repository được chỉ định.
- Không dùng credential registry lâu dài nhúng trong image.
- Có retention policy nhưng không xóa artifact đang được triển khai hoặc cần rollback.
- Có replication/cache nếu nền tảng yêu cầu artifact sẵn sàng ở region cụ thể.
- Ghi audit log cho publish, delete và pull khi dịch vụ hỗ trợ.

Với source package, giữ artifact cùng checksum và metadata để có thể triển khai lại chính xác. Không phụ thuộc một thư mục build tạm trên CI runner.

## 17. Các mô hình triển khai theo nền tảng

Các cloud provider có thể cung cấp nhiều con đường đóng gói khác nhau. Tên dịch vụ và chi tiết runtime thay đổi, nhưng có thể nhận diện ba mô hình tổng quát:

| Mô hình | Cách nhà phát triển cung cấp artifact | Trách nhiệm chính |
|---|---|---|
| Managed language runtime | Source package hoặc gói ngôn ngữ | Đúng handler, runtime version và dependency |
| Custom runtime | Source package kèm bootstrap/runtime adapter | Tương thích runtime contract và quản lý bootstrap |
| Container-based function | OCI image từ registry | Build image, entrypoint, runtime interface, patch và scan |

Ví dụ trong hệ sinh thái cloud:

- AWS Lambda hỗ trợ ZIP deployment package và container image; mỗi hình thức có yêu cầu handler/runtime hoặc image contract riêng.
- Azure Functions hỗ trợ triển khai package cho các runtime phù hợp và có mô hình custom container ở các hosting plan hỗ trợ.
- Google Cloud Functions thế hệ mới, còn được cung cấp trong hệ sinh thái Cloud Run functions, có thể build từ source bằng quy trình build được quản lý; Cloud Run cũng hỗ trợ triển khai container image.

Đây là ví dụ định hướng, không phải danh sách đầy đủ tính năng hoặc giới hạn hiện hành. Trước khi chọn, hãy kiểm tra runtime version, kiến trúc CPU, kích thước artifact, trigger, image protocol, registry location và hosting plan mà dịch vụ cụ thể hỗ trợ.

### 17.1. Managed build và tự build

Managed build giúp giảm công việc quản lý builder, runtime và dependency installation. Tuy nhiên, nhóm phát triển vẫn cần pin dependency và kiểm soát source revision, hiểu build log và build environment, kiểm tra artifact sau build, biết cách tạo lại artifact nếu cần rollback, và xác minh runtime cùng native dependency tương thích.

Tự build container image cho phép kiểm soát nhiều hơn nhưng đòi hỏi pipeline vá base image, scan, ký và quản lý registry.

## 18. Versioning, rollout và rollback

Artifact cần có định danh bất biến để nhóm vận hành biết chính xác hàm đang chạy nội dung nào. Có thể dùng semantic version, build number, commit SHA, checksum hoặc image digest.

Một bản phát hành nên liên kết source revision, artifact version và checksum/digest, runtime version và architecture, dependency lock file, function configuration, trigger mapping và execution identity, cùng kết quả kiểm thử và scan.

### 18.1. Tách artifact version khỏi function configuration

Artifact chứa mã và dependency; function configuration quyết định cách nền tảng thực thi. Hai phần có thể thay đổi độc lập nhưng phải được version hóa và review cùng nhau.

| Thành phần | Thay đổi | Cần build lại artifact? |
|---|---|---|
| Logic handler | Thay đổi | Có |
| Dependency | Thêm/cập nhật thư viện | Có |
| Base image | Thay đổi | Có |
| Runtime version do package yêu cầu | Thay đổi | Thường có hoặc cần build/kiểm thử lại |
| Environment variable không bí mật | Thay đổi | Thường không |
| Execution role/permission | Thay đổi | Không, nhưng cần kiểm thử quyền |
| Timeout/memory | Thay đổi | Không, nhưng cần kiểm thử hiệu năng |
| Trigger/concurrency | Thay đổi | Không, nhưng cần kiểm thử hành vi |

Không sửa nội dung artifact sau khi đã phát hành. Nếu cần thay code hoặc dependency, tạo artifact mới có version mới.

### 18.2. Canary và traffic shifting

Nếu nền tảng hỗ trợ version/alias hoặc traffic splitting, có thể phát hành phiên bản mới cho một phần traffic trước. Theo dõi invocation error rate, timeout và throttling, p95/p99 latency, cold-start latency, memory/CPU usage, downstream error và retry.

Chỉ tăng traffic khi số liệu đạt tiêu chí. Nếu lỗi tăng, chuyển traffic về version ổn định trước đó và giữ lại artifact lỗi để điều tra.

### 18.3. Rollback

Rollback cần artifact cũ còn tồn tại và tương thích với dữ liệu/configuration hiện tại. Nếu phiên bản mới đã thay đổi schema database hoặc format message, quay lại code cũ có thể không an toàn.

Trước khi rollout, xác định artifact ổn định trước đó, kiểm tra retention của package/image registry, xác định thay đổi schema có tương thích ngược không, kiểm tra trigger và quyền của version cũ, chuẩn bị thao tác traffic shift hoặc redeploy và ghi nhận điều kiện tự động dừng rollout.

## 19. Các lỗi thường gặp khi đóng gói và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Handler không tìm thấy | Sai module path, tên hàm hoặc package layout | Liệt kê archive, kiểm tra handler config và import path |
| Module import failed | Dependency thiếu hoặc sai phiên bản | Kiểm tra lock file, package contents và runtime logs |
| Native library load failed | Sai architecture, ABI hoặc thiếu shared library | Kiểm tra file binary, dynamic linker và base image |
| Image pull failed | Registry permission, digest sai hoặc image không tồn tại | Kiểm tra pull identity, repository và manifest |
| Container không khởi động | Sai entrypoint, command hoặc runtime interface | Kiểm tra startup logs và image contract |
| HTTPS certificate error | Thiếu CA bundle hoặc trust store sai | Kiểm tra certificate store và base image |
| Cold start tăng | Artifact lớn, import nặng hoặc initialization chậm | Đo download, bootstrap, import và dependency initialization |
| Chạy local được nhưng cloud lỗi | Môi trường local khác runtime/architecture cloud | Chạy smoke test trong image/runtime tương thích |
| Hết dung lượng tạm | Function ghi nhiều file vào temporary storage | Kiểm tra temporary storage usage và cleanup |
| Hành vi khác giữa staging/prod | Artifact được build khác hoặc config khác | So checksum/digest, runtime version và configuration |

### 19.1. Handler không được gọi

Kiểm tra theo thứ tự:

1. Artifact được publish đúng function/version chưa?
2. Cấu hình handler có đúng module và function không?
3. File handler có ở root hoặc package path runtime mong đợi không?
4. Runtime version có hỗ trợ syntax/API mà code dùng không?
5. Có lỗi import xảy ra trước khi handler được gọi không?
6. Trigger có gửi event đúng schema không?

### 19.2. Image pull hoặc startup failure

Kiểm tra registry authorization, image digest, architecture, manifest, entrypoint và runtime interface. Nếu nền tảng chạy image trong network riêng, xác minh image có thể được pull từ registry theo cơ chế provider hỗ trợ.

Không chẩn đoán chỉ dựa trên trạng thái deploy thành công. Deployment control plane có thể chấp nhận artifact nhưng invocation đầu tiên vẫn thất bại khi runtime tải image hoặc khởi tạo handler.

### 19.3. Cold start bất thường

Tách thời gian thành tải artifact, khởi động runtime, import, initialization và kết nối dependency. Nếu thời gian tải image chiếm phần lớn, tối ưu image/registry. Nếu import hoặc initialization chiếm phần lớn, giảm dependency, trì hoãn khởi tạo không cần thiết hoặc dùng connection strategy phù hợp.

## 20. Ví dụ thực tế: đóng gói hàm xử lý đơn hàng

Một hàm nhận sự kiện đơn hàng từ queue, kiểm tra payload, gọi dịch vụ inventory và ghi kết quả vào storage. Nhóm cần chọn giữa source package và container image.

### 20.1. Đánh giá yêu cầu

- Runtime Python managed của nền tảng đáp ứng phiên bản ứng dụng.
- Dependency chính là thư viện Python thuần.
- Không cần OS package đặc thù.
- Package có kích thước nhỏ.
- Hàm cần khởi động nhanh và triển khai thường xuyên.

Trong trường hợp này, source package là lựa chọn đơn giản. Nếu sau này cần thư viện native khó build hoặc runtime tùy chỉnh, nhóm có thể đánh giá container image.

### 20.2. Cấu trúc source package

~~~text
orders-function/
  app.py
  order_service.py
  requirements.txt
  tests/
~~~

Thư mục tests chỉ dùng cho pipeline và không đưa vào artifact production.

Dependency manifest:

~~~text
requests==2.32.3
pydantic==2.9.2
~~~

Handler:

~~~python
import json
from order_service import accept_order

def handle(event, context):
    order_id = event.get("order_id")
    if not order_id:
        raise ValueError("order_id is required")

    result = accept_order(order_id)
    return {
        "statusCode": 200,
        "body": json.dumps({"accepted": True, "result": result}),
    }
~~~

### 20.3. Pipeline đề xuất

1. Checkout commit đã review.
2. Cài runtime/toolchain tương ứng.
3. Cài dependency từ lock file.
4. Chạy unit test và handler test.
5. Tạo ZIP từ nội dung thư mục package.
6. Kiểm tra cấu trúc, checksum và kích thước ZIP.
7. Scan dependency và secret.
8. Publish artifact có version bất biến.
9. Deploy vào test environment và gửi queue event mẫu.
10. Kiểm tra acknowledgement, retry, latency và quyền truy cập.
11. Promote cùng artifact sang production.
12. Theo dõi metrics và giữ artifact trước đó cho rollback.

### 20.4. Khi chuyển sang container image

Nếu ứng dụng cần native image codec hoặc OS library đặc thù, nhóm có thể chuyển sang image. Khi đó:

- Chọn base image tương thích runtime và architecture.
- Cài OS package và dependency đã pin.
- Dùng multi-stage build nếu cần compiler.
- Cấu hình runtime interface theo function platform.
- Build image và publish theo digest.
- Scan image, tạo SBOM và ký nếu quy trình yêu cầu.
- Chạy local invocation test bằng harness phù hợp.
- Deploy thử và xác minh cold start trước khi chuyển production.

## 21. Checklist chọn và đóng gói function artifact

Trước khi phát hành, hãy xác nhận:

- [ ] Đã chọn source package hoặc container image dựa trên runtime và dependency thực tế.
- [ ] Handler và runtime contract khớp với nền tảng.
- [ ] Runtime version và architecture đã được xác định.
- [ ] Dependency manifest và lock file được quản lý trong source control.
- [ ] Native library tương thích OS, ABI và CPU.
- [ ] Source package không chứa test data, cache, credential hoặc file thừa.
- [ ] Container image dùng base image đáng tin cậy và có quy trình patch.
- [ ] Build context loại secret và file không cần thiết.
- [ ] Artifact có version, checksum hoặc digest bất biến.
- [ ] Package/image đã được inspect và test trong môi trường tương thích.
- [ ] Đã kiểm tra cold start, warm latency, memory và concurrency.
- [ ] Cấu hình môi trường và secret được quản lý ngoài artifact.
- [ ] Execution identity có quyền tối thiểu.
- [ ] SBOM, vulnerability scan và secret scan đã được thực hiện.
- [ ] Artifact được lưu ở repository/registry có kiểm soát truy cập.
- [ ] Staging và production dùng cùng artifact version/digest.
- [ ] Có kế hoạch canary, rollback và retention.

## 22. Quy trình vận hành lâu dài

1. **Inventory:** thống kê function, runtime, architecture và artifact đang triển khai.
2. **Dependency review:** theo dõi phiên bản thư viện, lỗ hổng và license.
3. **Runtime lifecycle:** theo dõi lịch hỗ trợ và ngừng hỗ trợ runtime của provider.
4. **Base image lifecycle:** cập nhật, rebuild và scan image định kỳ.
5. **Artifact retention:** giữ version phục vụ rollback và tuân thủ retention policy.
6. **Performance review:** đo cold start, warm latency, kích thước package/image và memory.
7. **Security review:** xác minh chữ ký, SBOM, quyền registry và secret handling.
8. **Recovery:** diễn tập redeploy artifact cũ và kiểm tra trigger/configuration.
9. **Retirement:** xóa artifact cũ theo chính sách sau khi xác minh không còn function/version phụ thuộc.

## 23. Ghi nhớ

Source package và container image là hai cách đóng gói hàm serverless với mức kiểm soát và trách nhiệm vận hành khác nhau. Source package phù hợp khi managed runtime đáp ứng và dependency đơn giản; container image hữu ích khi cần runtime, native library hoặc userspace tùy chỉnh.

Artifact phải khớp handler, runtime, OS/ABI và CPU architecture của nền tảng. Hãy build từ dependency lock file, loại file không cần thiết, kiểm thử trong môi trường tương thích và đo cold start. Với container image, quản lý base image, layers, registry, digest và runtime interface. Với cả hai hình thức, giữ cấu hình và secret ngoài artifact, dùng execution identity quyền tối thiểu, tạo SBOM/scan, phát hành artifact bất biến và promote cùng một artifact qua các môi trường. Quy trình đó giúp hàm dễ triển khai, dễ rollback và có thể truy vết khi xảy ra sự cố.
