# JDK trong container

Container cho phép đóng gói ứng dụng Java cùng môi trường chạy và cấu hình cần thiết thành một đơn vị có thể triển khai nhất quán trên máy lập trình viên, máy kiểm thử và máy chủ. Khi làm việc với Java trong container, cần phân biệt **container image**, **container đang chạy**, **JDK dùng để build** và **runtime dùng để chạy ứng dụng**. Những khái niệm này quyết định kích thước image, khả năng chẩn đoán, mức tiêu thụ tài nguyên và cách ứng dụng dừng an toàn.

Bài viết dùng Docker làm ví dụ vì đây là giao diện phổ biến để làm việc với OCI container image. Các nguyên tắc về image, process, resource limit và filesystem cũng áp dụng cho nhiều nền tảng container khác.

## 1. Container image và container

### Container image

**Container image** là gói bất biến ở góc nhìn sử dụng, gồm filesystem, metadata và cấu hình mặc định cần thiết để tạo container. Image thường được tạo từ nhiều layer. Mỗi lệnh build có thể tạo một layer hoặc thay đổi metadata; các layer được lưu trong cache và có thể dùng chung giữa nhiều image.

Một image Java thường chứa:

- Một hệ điều hành nền hoặc filesystem tối giản.
- JVM và các thư viện runtime.
- Tệp JAR, class file hoặc runtime image của ứng dụng.
- Metadata như working directory, user, entrypoint và command mặc định.

Image không phải là một máy ảo đầy đủ. Nó dùng kernel của hệ điều hành host thông qua cơ chế container của hệ điều hành.

### Container

**Container** là một thực thể được tạo từ image và đang được khởi chạy hoặc tồn tại ở trạng thái dừng. Container có process, filesystem có thể ghi riêng, cấu hình mạng và giới hạn tài nguyên riêng theo cấu hình runtime.

Có thể tạo nhiều container từ cùng một image. Các container thường chia sẻ layer chỉ đọc của image, nhưng mỗi container có writable layer riêng. Dữ liệu trong writable layer thường không phải nơi lưu trữ lâu dài; khi xóa container, phần dữ liệu riêng của nó cũng mất.

### Image, container và volume

| Thành phần | Vai trò | Vòng đời dữ liệu |
|---|---|---|
| Image | Mẫu filesystem và cấu hình để tạo container | Được lưu và tái sử dụng cho nhiều lần chạy |
| Container writable layer | Thay đổi phát sinh trong một container | Thường mất khi container bị xóa |
| Volume hoặc bind mount | Lưu dữ liệu bên ngoài vòng đời container | Có thể tồn tại sau khi container bị xóa |

Với ứng dụng Java, nên coi image là sản phẩm triển khai, container là tiến trình ứng dụng đang chạy, còn volume là nơi lưu dữ liệu cần tồn tại qua các lần thay thế container.

## 2. JDK image và runtime image

### Dùng JDK để biên dịch

JDK chứa compiler và các công cụ phát triển như javac, jar, javadoc, javap. Vì vậy, JDK image phù hợp cho giai đoạn build:

- Biên dịch mã nguồn Java thành class file.
- Đóng gói JAR.
- Chạy kiểm tra hoặc tác vụ build cần công cụ JDK.
- Phân tích dependency hoặc tạo runtime tùy biến bằng jlink.

Không nhất thiết phải mang toàn bộ JDK vào image production nếu ứng dụng chỉ cần chạy.

### Dùng JRE hoặc runtime image để chạy

Runtime image cần JVM và các thư viện mà ứng dụng cần để thực thi. Nó có thể đến từ JRE image do nhà cung cấp phát hành hoặc từ một runtime tùy biến được tạo bằng jlink.

Image runtime nhỏ hơn có thể giảm lượng dữ liệu phải tải và số thành phần không cần thiết. Đổi lại, các công cụ phát triển và chẩn đoán như javac hoặc jcmd có thể không hiện diện.

Cần phân biệt:

- **JDK image:** thuận tiện cho build và chẩn đoán, thường lớn hơn.
- **JRE/runtime image:** phù hợp để chạy ứng dụng, thường ít công cụ hơn.
- **Custom runtime image:** runtime được tạo có chọn lọc từ các module cần thiết, thường dùng jlink.

Việc chọn image nên dựa trên nhu cầu thực tế. Nếu ứng dụng cần JNI, agent, thư viện native hoặc công cụ chẩn đoán, hãy xác minh runtime image đã chọn có đủ thành phần tương thích.

## 3. Chọn base image

**Base image** là image nền được chỉ định trong lệnh FROM của Dockerfile. Base image Java thường được phát hành bởi nhà cung cấp JDK, ví dụ Eclipse Temurin hoặc các nhà cung cấp OpenJDK khác.

Ví dụ tên image thường gặp:

- eclipse-temurin:21-jdk: JDK 21, phù hợp để biên dịch.
- eclipse-temurin:21-jre: runtime Java 21, phù hợp để chạy ứng dụng.
- Các biến thể có hậu tố hệ điều hành hoặc kiến trúc: xác định môi trường nền cụ thể hơn.

Tên tag chỉ là ví dụ minh họa. Hãy kiểm tra tag còn được nhà cung cấp phát hành cho kiến trúc và nền tảng cần triển khai.

Khi chọn base image, cân nhắc:

1. **Phiên bản Java:** khớp với phiên bản mục tiêu mà ứng dụng được biên dịch và kiểm thử.
2. **Nhà cung cấp:** chọn vendor có chính sách cập nhật và hỗ trợ phù hợp.
3. **Hệ điều hành nền:** một số image dùng Debian/Ubuntu hoặc Alpine; thư viện native có thể phụ thuộc libc.
4. **Kiến trúc CPU:** image phải tương thích với máy triển khai, ví dụ linux/amd64 hoặc linux/arm64.
5. **Kích thước và công cụ:** image tối giản giúp giảm dung lượng nhưng có thể thiếu shell, package manager hoặc công cụ debug.
6. **Tính tái lập:** tag có thể được cập nhật theo thời gian. Với build cần tái lập nghiêm ngặt, cân nhắc pin phiên bản patch cụ thể hoặc image digest; đồng thời có quy trình cập nhật bảo mật có chủ đích.

### Alpine, glibc và musl

Alpine Linux thường được chọn vì image nền nhỏ và sử dụng musl libc. Nhiều ứng dụng Java thuần bytecode chạy tốt trên Alpine, nhưng thư viện native hoặc JNI có thể được biên dịch để phụ thuộc glibc. Khi dùng Alpine, cần kiểm thử các thành phần native, agent, công cụ giám sát và thư viện hệ thống.

Image dựa trên Debian hoặc Ubuntu thường dùng glibc và có thể tương thích hơn với các thư viện native phổ biến. Kích thước image chỉ là một yếu tố; khả năng tương thích và vận hành ổn định cũng quan trọng.

### Distroless và image tối giản

Image tối giản hoặc distroless thường chỉ giữ runtime và những tệp cần thiết. Một số image không có shell hay package manager. Điều này giảm bề mặt tấn công và dung lượng, nhưng làm cho cách debug trực tiếp bên trong container khác đi. Nên có quy trình quan sát qua log, metrics, JFR hoặc image debug riêng.

## 4. Dockerfile và multi-stage build

**Dockerfile** mô tả cách tạo image. Một Dockerfile có thể có nhiều stage. **Multi-stage build** dùng một stage có JDK để biên dịch, sau đó chỉ sao chép artifact cần chạy sang stage runtime.

Cách này giúp image cuối không phải mang theo mã nguồn, compiler, cache build hoặc các công cụ chỉ cần trong giai đoạn phát triển.

### Ví dụ ứng dụng Java nhỏ

Cấu trúc thư mục:

~~~text
jdk-container-demo/
├── Dockerfile
├── .dockerignore
└── src/
    └── com/
        └── example/
            └── Main.java
~~~

Tệp Main.java:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from Java in a container!");
    }
}
~~~

Dockerfile:

~~~dockerfile
# Stage 1: compile with a full JDK
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace
COPY src ./src
RUN mkdir -p /out && javac --release 21 -d /out src/com/example/Main.java

# Stage 2: run with a smaller runtime image
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build --chown=10001:10001 /out/ /app/
USER 10001:10001
ENTRYPOINT ["java", "-cp", "/app", "com.example.Main"]
~~~

Tệp .dockerignore:

~~~text
.git
.idea
*.iml
target
build
.gradle
.env
~~~

Build image từ thư mục gốc dự án:

~~~bash
docker build -t jdk-container-demo:local .
~~~

Chạy container:

~~~bash
docker run --rm --name jdk-container-demo jdk-container-demo:local
~~~

Output:

~~~text
Hello from Java in a container!
~~~

Giải thích:

- Stage build dùng JDK 21 để biên dịch mã nguồn bằng javac.
- Tùy chọn --release 21 đặt mức API Java và class file mục tiêu là Java 21.
- Tùy chọn -d /out đặt class file trong thư mục đầu ra.
- Stage runtime dùng image JRE 21.
- COPY --from=build chỉ sao chép class file đã biên dịch từ stage trước.
- --chown đặt quyền sở hữu các tệp được sao chép cho UID/GID 10001.
- USER chạy tiến trình với UID/GID không phải root.
- ENTRYPOINT dạng JSON (exec form) khởi chạy Java trực tiếp, không đi qua shell.

Ví dụ giả định Docker đã được cài đặt, daemon đang chạy và tag base image được hỗ trợ trên nền tảng hiện tại. Với dự án thực tế, thay lệnh javac đơn lẻ bằng quy trình build Maven hoặc Gradle phù hợp, rồi chỉ sao chép JAR hoặc runtime artifact cần thiết sang stage cuối.

## 5. Layer, build context và cache

Docker gửi **build context** đến builder. Dấu chấm trong lệnh docker build -t ten-image . nghĩa là thư mục hiện tại là build context. Những tệp trong context có thể được dùng bởi lệnh COPY hoặc ADD.

Tệp .dockerignore loại bỏ những thứ không cần gửi vào build context, ví dụ:

- Thư mục .git, IDE metadata và tệp tạm.
- Thư mục build output cũ như target hoặc build.
- Cache phụ thuộc không cần thiết.
- Tệp cấu hình cục bộ hoặc thông tin bí mật.

**Layer cache** cho phép builder tái sử dụng kết quả của những bước build không thay đổi. Với dự án Maven hoặc Gradle, nên bố trí Dockerfile sao cho các tệp mô tả dependency được sao chép trước mã nguồn, sau đó mới tải dependency và biên dịch. Khi chỉ thay mã nguồn, các bước tải dependency có thể được cache lại.

Không nên đưa toàn bộ thư mục làm việc, thư mục .git hoặc secret vào image. Một secret từng được COPY vào layer có thể vẫn tồn tại trong lịch sử image kể cả khi một layer sau xóa tệp đó.

## 6. Cấu hình ứng dụng và dữ liệu

### Environment variable

Có thể truyền cấu hình không nhạy cảm bằng biến môi trường:

~~~bash
docker run --rm -e APP_MODE=production jdk-container-demo:local
~~~

Ứng dụng Java có thể đọc bằng System.getenv("APP_MODE"). Nên giữ cấu hình môi trường bên ngoài image để cùng một artifact có thể chạy ở development, test và production.

### Secret

Không nên ghi mật khẩu, token hoặc private key vào Dockerfile, mã nguồn, image layer hay build argument thông thường. Biến môi trường cũng có thể bị lộ qua công cụ inspect, cấu hình tiến trình hoặc hệ thống log. Hãy dùng secret mount hoặc cơ chế quản lý secret của nền tảng triển khai, giới hạn quyền truy cập và luân chuyển secret theo chính sách.

### Volume và bind mount

Container filesystem có thể bị thay thế khi triển khai phiên bản mới. Nếu ứng dụng cần lưu dữ liệu lâu dài, hãy dùng volume hoặc dịch vụ lưu trữ bên ngoài. Ví dụ mount một thư mục dữ liệu:

~~~bash
docker run --rm -v app-data:/app/data jdk-container-demo:local
~~~

Trong ví dụ này, app-data là named volume do Docker quản lý. Với ứng dụng production, cần xác định rõ dữ liệu nào là tạm thời, dữ liệu nào phải tồn tại lâu dài và ai chịu trách nhiệm backup.

### Logging

Ứng dụng container thường ghi log ra stdout và stderr để runtime thu thập. Tránh chỉ ghi log vào tệp trong writable layer của container vì log có thể mất khi container bị thay thế. Nếu cần log file, hãy cấu hình nơi lưu trữ và chính sách rotation rõ ràng.

## 7. JVM và giới hạn tài nguyên container

Container có thể được giới hạn CPU và bộ nhớ. JVM cần nhìn thấy các giới hạn này để chọn heap, số luồng và các cấu hình runtime phù hợp.

### Memory limit và Java heap

Ví dụ giới hạn bộ nhớ và CPU cho container:

~~~bash
docker run --rm --memory=512m --cpus=1.5 jdk-container-demo:local
~~~

Với các bản HotSpot hiện đại trên Linux, JVM có khả năng nhận biết giới hạn tài nguyên của container thông qua cgroup. Hành vi cụ thể phụ thuộc phiên bản JDK, nhà cung cấp, kernel và cấu hình container.

Không nên mặc định toàn bộ memory limit của container đều dành cho Java heap. Tổng mức dùng bộ nhớ của tiến trình có thể bao gồm:

- Java heap: đối tượng Java được cấp phát.
- Metaspace: metadata của lớp.
- Thread stack: bộ nhớ stack của các luồng.
- Direct buffer và các vùng native memory.
- JIT code cache, thư viện native, GC structures và thành phần runtime khác.

Nếu đặt Xmx bằng toàn bộ memory limit, tiến trình vẫn có thể vượt giới hạn container do phần native và non-heap, rồi bị hệ điều hành kết thúc vì OOM.

Có thể điều chỉnh tỷ lệ heap tối đa theo dung lượng RAM JVM nhận biết:

~~~bash
docker run --rm --memory=512m --cpus=1.5 \
  -e JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0" \
  jdk-container-demo:local
~~~

MaxRAMPercentage đặt tỷ lệ phần trăm bộ nhớ tối đa JVM được phép dùng làm heap. Giá trị 60.0 chỉ là ví dụ; cần đo mức dùng thực tế và dành đủ bộ nhớ cho native, metaspace, thread stack, buffer, GC và agent. Không có một tỷ lệ phù hợp cho mọi ứng dụng.

Nếu muốn kiểm tra thông tin hệ thống mà JVM nhận biết trên JDK hỗ trợ tùy chọn này:

~~~bash
java -XshowSettings:system -version
~~~

Lệnh in thông tin hệ thống và tài nguyên mà JVM nhìn thấy. Cần đối chiếu với memory limit và CPU quota thực tế của container.

### CPU limit

Giới hạn CPU ảnh hưởng đến số processor mà JVM và ứng dụng nhìn thấy. Một số cơ chế như garbage collection, common ForkJoinPool và thread pool có thể dựa trên số processor khả dụng. Nếu số CPU được nhận biết không phù hợp với quota thực tế, có thể xem xét cờ -XX:ActiveProcessorCount=N trên JDK hỗ trợ. Chỉ đặt cờ này sau khi đo và hiểu tác động đến ứng dụng.

### OOM và chẩn đoán bộ nhớ

Nếu container bị kết thúc vì vượt memory limit, có thể không có Java OutOfMemoryError trong log vì kernel hoặc runtime đã kết thúc tiến trình. Hãy kiểm tra trạng thái container, sự kiện OOM, memory usage, heap configuration và native memory. Phân biệt Java heap exhaustion với container-level OOM là bước quan trọng khi điều tra sự cố.

## 8. Process, signal và shutdown an toàn

Container thường được thiết kế để chạy một process chính. Khi chạy Java, nên để JVM trở thành process chính của container.

Dạng ENTRYPOINT JSON trong ví dụ trước:

~~~dockerfile
ENTRYPOINT ["java", "-cp", "/app", "com.example.Main"]
~~~

là **exec form**. Nó gọi Java trực tiếp. Dạng shell form có thể thêm shell làm process trung gian, khiến việc chuyển signal và quản lý process phức tạp hơn.

Khi yêu cầu dừng container, Docker thường gửi SIGTERM đến process chính và chờ trong khoảng grace period trước khi gửi SIGKILL. JVM có thể chạy **shutdown hook** khi nhận tín hiệu dừng phù hợp. Ứng dụng nên dùng hook hoặc cơ chế lifecycle của framework để:

- Ngừng nhận công việc mới.
- Hoàn tất hoặc hủy công việc đang xử lý theo thời hạn.
- Flush log và dữ liệu cần thiết.
- Đóng connection pool, executor và tài nguyên.
- Thoát trước khi grace period kết thúc.

Có thể yêu cầu thời gian dừng cụ thể:

~~~bash
docker stop --time 30 ten-container
~~~

Thời gian này cần phù hợp với thời gian shutdown của ứng dụng và chính sách triển khai. Nếu ứng dụng cần nhiều thời gian hơn, hãy cấu hình grace period ở nền tảng orchestration tương ứng.

## 9. Chẩn đoán ứng dụng Java trong container

Nên kết hợp thông tin từ ứng dụng, JVM và container runtime:

| Công cụ hoặc lệnh | Dùng để |
|---|---|
| docker logs | Đọc stdout và stderr của container |
| docker stats | Quan sát CPU, memory, network và block I/O |
| docker inspect | Xem cấu hình, trạng thái, mount và giới hạn container |
| docker exec | Chạy lệnh trong một container đang hoạt động |
| jcmd | Gửi lệnh chẩn đoán đến JVM |
| jstack | Lấy thread dump |
| jmap | Thu thập thông tin heap hoặc heap dump theo khả năng phiên bản |
| jfr | Ghi và phân tích sự kiện Java Flight Recorder |

Ví dụ lấy phiên bản JVM trong container đang chạy và có JDK tools:

~~~bash
docker exec ten-container jcmd 1 VM.version
~~~

Lệnh giả định ứng dụng Java là PID 1 trong container và image có jcmd. Nếu image runtime không chứa công cụ này, có thể dùng image debug riêng hoặc một phương án quan sát phù hợp với nền tảng. Công cụ attach cũng có thể bị giới hạn bởi user, namespace, quyền tiến trình và cấu hình JVM.

Không nên thêm toàn bộ JDK và shell vào image production chỉ để tiện debug nếu điều đó không phù hợp với yêu cầu bảo mật. Hãy xác định trước quy trình chẩn đoán: log, metrics, JFR, heap dump, thread dump và nơi lưu artifact chẩn đoán.

## 10. Bảo mật và vận hành image Java

Một số nguyên tắc nên áp dụng khi xây dựng image:

1. **Chạy non-root:** dùng USER với UID/GID phù hợp, cấp quyền ghi chỉ cho các thư mục thực sự cần thiết.
2. **Dùng multi-stage build:** loại bỏ compiler, cache build và mã nguồn khỏi image runtime nếu không cần.
3. **Giữ base image được cập nhật:** theo dõi bản vá bảo mật của JDK và hệ điều hành nền.
4. **Pin phiên bản có chủ đích:** tag cụ thể hoặc digest giúp tái lập; đồng thời cần quy trình nâng cấp để nhận bản vá mới.
5. **Không đóng gói secret:** truyền secret qua hệ thống quản lý secret và giới hạn phạm vi truy cập.
6. **Giới hạn quyền container:** tránh cấp privileged hoặc quyền hệ thống không cần thiết.
7. **Giữ filesystem tối giản:** chỉ thêm package, tệp và thư viện cần thiết.
8. **Quan sát tài nguyên:** cấu hình memory/CPU limit phù hợp, theo dõi OOM và thời gian shutdown.
9. **Kiểm tra image theo kiến trúc đích:** đặc biệt khi có JNI hoặc thư viện native.
10. **Tách cấu hình khỏi artifact:** cùng một image nên có thể triển khai ở nhiều môi trường bằng cấu hình bên ngoài.

Nếu bật filesystem read-only, cần xác định trước ứng dụng có ghi vào /tmp, thư mục log hoặc thư mục dữ liệu nào. Những đường dẫn cần ghi phải được cấp writable mount hoặc tmpfs có giới hạn phù hợp.

## 11. Lỗi thường gặp

### Container bị OOM dù heap chưa đầy

Memory limit áp dụng cho toàn bộ tiến trình và các thành phần bộ nhớ liên quan, không chỉ Java heap. Kiểm tra heap, metaspace, direct buffer, thread stack, native memory và mức dùng thực tế. Điều chỉnh Xmx hoặc MaxRAMPercentage để chừa headroom.

### Chạy được trên máy cá nhân nhưng lỗi trong container

Nguyên nhân có thể là khác phiên bản JDK, thiếu thư viện native, khác kiến trúc CPU, thiếu file cấu hình, đường dẫn tương đối khác hoặc biến môi trường chưa được truyền. Hãy kiểm tra image thực tế, JDK version, filesystem và cấu hình runtime.

### Image production không có javac hoặc jcmd

Đây có thể là chủ ý của runtime image tối giản. Dùng JDK ở build stage và thiết kế quy trình debug riêng. Không giả định mọi image Java đều chứa đầy đủ JDK tools.

### Ứng dụng không dừng đúng hạn

Kiểm tra ENTRYPOINT có dùng exec form hay không, JVM có nhận SIGTERM không, shutdown hook có hoàn tất trong grace period không và ứng dụng có chặn luồng shutdown bởi tác vụ không kết thúc hay không.

### Thư viện native không tải được trên Alpine

Kiểm tra thư viện được biên dịch cho musl hay glibc, kiến trúc CPU, dependency hệ thống và phiên bản ABI. Thử base image tương thích với thư viện trước khi thay đổi code ứng dụng.

### Mỗi lần build đều tải lại dependency

Sắp xếp Dockerfile để các bước dependency được cache trước bước COPY mã nguồn. Đảm bảo build context không thay đổi không cần thiết và .dockerignore loại các thư mục sinh ra cục bộ.

### Dữ liệu biến mất sau khi deploy

Container writable layer có vòng đời gắn với container. Chuyển dữ liệu cần lưu lâu dài sang volume, database hoặc object storage; xác định backup và migration riêng.

## 12. Checklist triển khai Java trong container

- Chọn đúng JDK version và vendor cho dự án.
- Dùng JDK image để build; cân nhắc JRE hoặc custom runtime image cho production.
- Tạo multi-stage build để image cuối chỉ chứa artifact cần chạy.
- Đặt .dockerignore để loại build output, cache, IDE files và secret khỏi build context.
- Dùng exec form cho ENTRYPOINT để JVM nhận signal trực tiếp.
- Chạy ứng dụng bằng UID/GID không phải root.
- Đưa cấu hình ra ngoài image và dùng secret manager cho thông tin nhạy cảm.
- Lưu dữ liệu cần tồn tại lâu dài ở volume hoặc dịch vụ lưu trữ bên ngoài.
- Đặt memory/CPU limit và xác minh JVM nhận biết giới hạn container.
- Chừa bộ nhớ cho native và non-heap khi chọn Xmx hoặc MaxRAMPercentage.
- Đảm bảo ứng dụng xử lý SIGTERM và shutdown trong grace period.
- Ghi log ra stdout/stderr và chuẩn bị quy trình lấy JFR, thread dump hoặc heap dump.
- Kiểm tra image trên đúng kiến trúc CPU và môi trường triển khai.
- Theo dõi cập nhật bảo mật của JDK và base image.

## 13. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Container image | Gói filesystem và metadata dùng để tạo container |
| Container | Thực thể chạy process từ image với cấu hình riêng |
| Base image | Image nền được dùng trong Dockerfile |
| Build stage | Giai đoạn tạo artifact, thường dùng JDK |
| Runtime image | Image chứa môi trường cần để chạy ứng dụng |
| Multi-stage build | Quy trình build nhiều stage và chỉ chuyển artifact cần thiết sang stage cuối |
| Build context | Tập tệp builder nhận khi chạy docker build |
| Layer cache | Cơ chế tái sử dụng kết quả các bước build |
| Volume | Vùng lưu trữ tách khỏi vòng đời container |
| cgroup | Cơ chế kernel dùng để nhóm và giới hạn tài nguyên process |
| Container awareness | Khả năng JVM nhận biết CPU và memory limit của container |
| MaxRAMPercentage | Cờ đặt tỷ lệ RAM tối đa JVM dùng cho heap |
| Exec form | Cách khai báo command dạng JSON để chạy process trực tiếp |
| SIGTERM | Tín hiệu yêu cầu process dừng có kiểm soát |
| Shutdown hook | Hook JVM có thể chạy trong quá trình shutdown |
| JNI | Cơ chế Java gọi mã native |
| jlink | Công cụ tạo runtime image từ các module được chọn |
| Distroless | Phong cách image chỉ giữ runtime và tệp ứng dụng cần thiết |

Khi đóng gói một ứng dụng Java, hãy lần lượt xác định **JDK nào dùng để build, runtime nào dùng để chạy, tài nguyên container được giới hạn ra sao, và JVM sẽ nhận tín hiệu dừng như thế nào**. Bốn câu hỏi này giúp thiết kế image gọn, chạy ổn định và dễ chẩn đoán hơn.