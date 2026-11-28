# Chọn bản phân phối JDK hỗ trợ musl còn được bảo trì

Khi chạy Java trên Alpine Linux, cần chọn một bản phân phối JDK có binary được xây dựng và kiểm thử cho `musl libc`. Một JDK chỉ ghi chung là hỗ trợ Linux hoặc có thể chạy trên container không đủ để chứng minh nó tương thích với Alpine. Hãy kiểm tra ma trận nền tảng, lịch cập nhật bảo mật, thời hạn hỗ trợ của phiên bản Java, kiến trúc CPU và các image tag do chính nhà cung cấp duy trì.

Tại thời điểm cập nhật bài học (tháng 11/2026), các lựa chọn thực tế cho ứng dụng mới gồm Eclipse Temurin, Amazon Corretto và BellSoft Liberica. Java 25 là LTS mới nhất; Java 21 vẫn là LTS phù hợp nếu ứng dụng hoặc thư viện chưa sẵn sàng nâng lên Java 25. Java 16 là feature release đã kết thúc hỗ trợ thông thường, vì vậy không nên chọn JDK 16 cho triển khai production mới chỉ để giữ đúng phiên bản của bài học.

## 1. Tiêu chí chọn một JDK musl được duy trì

Một bản phân phối phù hợp cần đáp ứng đồng thời các tiêu chí sau:

1. **Có bản dựng musl được công bố rõ ràng:** tài liệu phải chỉ rõ Alpine/musl hoặc Linux musl, không suy ra từ một tag Linux chung.
2. **Còn nhận bản vá:** nhà cung cấp vẫn phát hành CPU/security update cho major version đang chọn và cho image/base OS tương ứng.
3. **Có thời hạn hỗ trợ phù hợp:** ưu tiên LTS cho dịch vụ cần vận hành lâu dài; kiểm tra ngày kết thúc hỗ trợ của chính nhà cung cấp.
4. **Đúng kiến trúc:** xác nhận image có `linux/amd64`, `linux/arm64` hoặc kiến trúc mà cụm máy thực tế sử dụng.
5. **Phụ thuộc native tương thích:** JNI, JNA, agent, thư viện `.so` và executable phụ trợ phải hoạt động với musl.
6. **Mức hỗ trợ phù hợp:** phân biệt hỗ trợ cộng đồng với hỗ trợ thương mại có SLA hoặc hợp đồng xử lý sự cố.
7. **Image có thể cập nhật và kiểm soát:** dùng tag cụ thể, theo dõi digest, quét lỗ hổng và có lịch nâng bản vá.

Không nên chỉ nhìn vào kích thước image hoặc tên thương hiệu. Một image nhỏ nhưng không có bản vá phù hợp, thiếu kiến trúc cần triển khai hoặc không chạy được native dependency sẽ làm tăng chi phí vận hành.

## 2. Những lựa chọn đang có bản dựng Alpine/musl

### Eclipse Temurin

Eclipse Temurin do Adoptium phát hành. Docker Official Images hiện có các tag Alpine cho Java 17, 21 và 25, với cả biến thể JDK và JRE. Ví dụ tag Java 25 gồm:

```text
eclipse-temurin:25-jdk-alpine-3.24
eclipse-temurin:25-jre-alpine-3.24
```

Có thể ghim patch release cụ thể, ví dụ `25.0.5.1_2-jdk-alpine-3.24`, thay vì chỉ dùng tag major `25-jdk-alpine`. Adoptium công bố lịch cập nhật theo chu kỳ OpenJDK và cam kết hỗ trợ các bản LTS ít nhất bốn năm. Hỗ trợ trực tiếp của Adoptium là hỗ trợ cộng đồng; nếu cần SLA thương mại, cần chọn nhà cung cấp dịch vụ hỗ trợ Temurin được Adoptium liệt kê.

Temurin phù hợp khi đội phát triển muốn một bản OpenJDK phổ biến, quy trình phát hành minh bạch và image JDK/JRE Alpine có sẵn. Nên kiểm tra lại tag theo kiến trúc và phiên bản Alpine đích trước mỗi lần nâng cấp.

### Amazon Corretto

Amazon Corretto là bản phân phối OpenJDK miễn phí, có lịch LTS do AWS công bố. AWS xác nhận các bản Corretto 17, 21 và 25 hỗ trợ Linux dùng musl trên Alpine Linux 3.21 trở lên. Docker Official Images có tag JDK theo từng phiên bản Alpine, ví dụ:

```text
amazoncorretto:25-alpine3.24-jdk
amazoncorretto:21-alpine3.24-jdk
```

Theo lịch hỗ trợ Corretto được AWS công bố tại thời điểm cập nhật bài học, Corretto 25 LTS dự kiến nhận bản cập nhật đến tháng 7/2032 và kết thúc hỗ trợ vào tháng 10/2032; Corretto 21 LTS dự kiến kết thúc hỗ trợ vào tháng 10/2030. AWS lên kế hoạch cập nhật định kỳ hàng quý và có thể phát hành bản sửa lỗi khẩn cấp ngoài chu kỳ này.

Corretto là lựa chọn đáng cân nhắc khi cần LTS miễn phí có lịch hỗ trợ dài, đặc biệt với workload chạy trên AWS. Tuy vậy, vẫn phải kiểm tra đúng tag Alpine và phiên bản Alpine được hỗ trợ; một image Corretto dựa trên Amazon Linux hoặc Debian không phải là image musl.

### BellSoft Liberica JDK

BellSoft cung cấp image Liberica JDK và JRE cho Alpine, trong đó có repository nêu rõ biến thể musl:

```text
bellsoft/liberica-openjdk-alpine-musl:25
bellsoft/liberica-openjre-alpine-musl:25
```

BellSoft công bố image cho x86_64 và AArch64/arm64. Danh sách tag có các dòng LTS như Java 17, 21 và 25; repository Alpine musl được cập nhật thường xuyên. BellSoft cũng cung cấp các lựa chọn hỗ trợ Liberica thương mại. Nếu cần hợp đồng hỗ trợ, hãy xác nhận phiên bản Java, hệ điều hành, kiến trúc và thời gian phản hồi được bao gồm trong gói hỗ trợ cụ thể.

Liberica phù hợp khi cần lựa chọn image musl rõ ràng, cần nhiều tùy chọn registry hoặc muốn đánh giá hỗ trợ từ nhà cung cấp JDK. Khi sử dụng, nên kiểm tra tag và digest của đúng repository `alpine-musl`, tránh nhầm với repository Alpine hoặc Linux có cấu hình libc khác.

## 3. So sánh theo nhu cầu vận hành

| Bản phân phối | Ví dụ tag Alpine/musl | Chính sách hỗ trợ đáng chú ý | Phù hợp khi |
|---|---|---|---|
| Eclipse Temurin | `eclipse-temurin:25-jdk-alpine-3.24` | LTS được Adoptium hỗ trợ ít nhất 4 năm; hỗ trợ cộng đồng, SLA qua đối tác | Muốn bản OpenJDK phổ biến, image JDK/JRE rõ ràng và cộng đồng rộng |
| Amazon Corretto | `amazoncorretto:25-alpine3.24-jdk` | Corretto 25 LTS dự kiến cập nhật đến 2032; cập nhật định kỳ miễn phí | Cần thời hạn LTS dài, đặc biệt trong môi trường AWS |
| BellSoft Liberica | `bellsoft/liberica-openjdk-alpine-musl:25` | Có image musl cho x86_64/arm64 và tùy chọn hỗ trợ thương mại | Cần repository musl chuyên biệt hoặc muốn đánh giá hỗ trợ trực tiếp từ nhà cung cấp |

Các tag trong bảng là ví dụ có thật trong danh sách image tại thời điểm viết, không phải lời cam kết tag sẽ tồn tại vĩnh viễn. Tag major như `25` có thể trỏ đến patch mới sau này. Với build production có yêu cầu tái lập, hãy ghim patch release và digest sau khi kiểm thử.

## 4. Nên chọn Java 25 LTS hay Java 21 LTS?

Java 25 là LTS hiện hành và là điểm bắt đầu hợp lý cho hệ thống mới nếu framework, thư viện, agent và công cụ build đều hỗ trợ. Java 21 vẫn là lựa chọn LTS tốt khi ứng dụng đang chạy ổn định trên 21 hoặc một dependency chưa tương thích với 25.

| Phiên bản | Tình trạng | Hướng sử dụng |
|---|---|---|
| Java 25 | LTS hiện hành | Ưu tiên cho dự án mới sau khi kiểm tra tương thích |
| Java 21 | LTS đang được duy trì | Dùng cho hệ thống cần giữ nền tảng 21 hoặc cần lộ trình nâng cấp từng bước |
| Java 17 | LTS cũ hơn, vẫn có nhà cung cấp duy trì | Dùng khi framework hoặc sản phẩm còn yêu cầu 17; lập kế hoạch nâng cấp |
| Java 27 | Feature release, không phải LTS | Chỉ chọn khi có lý do dùng feature mới và chấp nhận chu kỳ nâng cấp ngắn |
| Java 16 | Đã hết vòng đời hỗ trợ thông thường | Không dùng làm runtime production mới |

Đừng suy ra lịch hỗ trợ của một JDK từ lịch upstream chung. Mỗi nhà cung cấp có thể cam kết thời gian cập nhật khác nhau. Ví dụ, Adoptium công bố thời gian hỗ trợ LTS tối thiểu bốn năm, trong khi AWS công bố lịch riêng cho từng bản Corretto. Hãy ghi rõ nhà cung cấp và ngày kết thúc hỗ trợ trong hồ sơ vận hành của ứng dụng.

## 5. Chọn JDK hay JRE image?

JDK cần thiết ở giai đoạn biên dịch và khi ứng dụng cần các công cụ như `javac`, `jlink`, `jcmd` hoặc `jstack`. Runtime production chỉ cần chạy ứng dụng thường có thể dùng JRE image hoặc runtime tùy chỉnh để giảm các công cụ không cần thiết.

Với Temurin, có tag JDK và JRE Alpine riêng. Ví dụ Dockerfile multi-stage:

```dockerfile
FROM eclipse-temurin:25.0.5.1_2-jdk-alpine-3.24 AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -B -DskipTests package

FROM eclipse-temurin:25.0.5.1_2-jre-alpine-3.24 AS runtime
WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Hai stage dùng cùng dòng Java và cùng phiên bản Alpine, giúp tránh khác biệt môi trường libc giữa lúc build và lúc chạy. Nếu ứng dụng có JNI, thư viện native hoặc agent, cần xác nhận các file native được build cho đúng kiến trúc và musl của runtime stage.

Không phải nhà cung cấp nào cũng công bố cùng một bộ tag JDK/JRE cho mọi major version và kiến trúc. Trước khi dùng JRE tag, hãy kiểm tra tag đó thực sự tồn tại. Nếu cần tự tạo runtime bằng `jlink`, dùng JDK đúng target musl để tạo runtime image.

## 6. Kiểm tra tag, kiến trúc và libc trước khi chốt

Không nên chọn tag chỉ vì tên có chữ `alpine`. Hãy xác nhận image thuộc đúng nhà cung cấp, phiên bản Java, phiên bản Alpine và kiến trúc cần dùng.

Ví dụ với Temurin:

```sh
docker pull eclipse-temurin:25-jdk-alpine-3.24
docker run --rm eclipse-temurin:25-jdk-alpine-3.24 java -version
docker run --rm eclipse-temurin:25-jdk-alpine-3.24 sh -c "ldd --version; apk info musl; uname -m"
```

Kiểm tra manifest nhiều kiến trúc:

```sh
docker buildx imagetools inspect eclipse-temurin:25-jdk-alpine-3.24
```

Với Corretto, có thể kiểm tra tag cụ thể trong Docker Official Images và chạy tương tự:

```sh
docker pull amazoncorretto:25-alpine3.24-jdk
docker run --rm amazoncorretto:25-alpine3.24-jdk java -version
```

Với Liberica, chọn đúng repository musl:

```sh
docker pull bellsoft/liberica-openjdk-alpine-musl:25
docker run --rm bellsoft/liberica-openjdk-alpine-musl:25 java -version
```

Các lệnh này xác nhận image tải được và JVM khởi động. Chúng chưa chứng minh toàn bộ ứng dụng tương thích; vẫn cần chạy integration test với thư viện native thực tế.

## 7. Kiểm tra lịch bảo trì và quy trình cập nhật

Một image có tag mới không tự động có nghĩa mọi thành phần bên trong đều được vá. Hãy theo dõi cả JDK, base Alpine, package hệ thống và native dependency.

Quy trình đề xuất:

1. Ghi lại vendor, major version, tag đầy đủ, digest, kiến trúc và base Alpine.
2. Đăng ký lịch theo dõi CPU/security release của nhà cung cấp JDK.
3. Theo dõi bản vá của Alpine và cập nhật package hệ thống khi cần.
4. Quét image bằng công cụ bảo mật của tổ chức, sau đó phân loại CVE theo package thực tế và khả năng khai thác.
5. Build lại image từ tag/digest mới, chạy unit test và integration test trong đúng container musl.
6. Triển khai canary hoặc theo từng nhóm workload, theo dõi lỗi khởi động, nạp thư viện native, TLS, DNS và hiệu năng.
7. Lưu digest đã triển khai để có thể tái lập hoặc rollback.

Ví dụ, tag `25-jdk-alpine-3.24` có thể được cập nhật sang patch JDK mới trong khi tên tag giữ nguyên. Vì vậy, chỉ ghim major tag là chưa đủ để tái lập chính xác một bản build. Có thể dùng tag patch cụ thể kết hợp digest; vẫn cần cập nhật digest theo chu kỳ vá bảo mật.

## 8. Những trường hợp nên chọn image glibc

Nếu một thư viện native thiết yếu chỉ phát hành binary glibc, hoặc nhà cung cấp không hỗ trợ musl cho kiến trúc cần dùng, hãy chọn bản phân phối JDK trên image glibc như Debian, Ubuntu hoặc UBI. Không nên cố giữ Alpine bằng cách chép thư viện glibc vào image musl hay cài lớp tương thích mà chưa có xác nhận từ nhà cung cấp.

Trước khi quyết định, lập danh sách các thành phần native:

- JNI/JNA do ứng dụng hoặc thư viện bên thứ ba cung cấp.
- Java agent, profiler và APM agent.
- Native transport, thư viện nén, ảnh, mật mã hoặc database client.
- Executable được gọi qua `ProcessBuilder`.
- Công cụ giám sát và chẩn đoán có binary native.

Nếu bất kỳ thành phần bắt buộc nào không có bản musl được duy trì, image glibc thường là lựa chọn dễ vận hành và hỗ trợ hơn.

## 9. Quyết định mẫu

Với một dịch vụ mới, có thể áp dụng quy tắc sau:

- Chọn Java 25 LTS nếu framework và các dependency đã xác nhận tương thích.
- Chọn Corretto 25 nếu ưu tiên lịch LTS dài, cập nhật miễn phí và hệ sinh thái AWS.
- Chọn Temurin 25 nếu muốn bản OpenJDK cộng đồng phổ biến và image Alpine JDK/JRE rõ ràng.
- Chọn Liberica 25 nếu cần repository musl chuyên biệt hoặc cần đánh giá lựa chọn hỗ trợ thương mại của BellSoft.
- Chọn Java 21 LTS nếu chưa thể nâng ứng dụng lên 25.
- Chọn image glibc nếu native stack không hỗ trợ musl.

Đây là điểm khởi đầu để đánh giá, không thay thế việc kiểm thử ứng dụng và xác nhận điều khoản hỗ trợ của nhà cung cấp. Kết quả lựa chọn cần ghi rõ phiên bản Java, vendor, tag/digest, Alpine version, kiến trúc, thời hạn hỗ trợ và người chịu trách nhiệm cập nhật.

## 10. Ghi nhớ

- Hãy chọn JDK có bản dựng musl được nhà cung cấp công bố rõ ràng.
- Temurin, Corretto và Liberica hiện có các image hoặc binary phù hợp với Alpine/musl cho các dòng LTS mới.
- Java 25 LTS là lựa chọn mặc định hợp lý cho dự án mới; Java 21 LTS vẫn phù hợp khi cần tương thích.
- Phân biệt hỗ trợ cộng đồng, lịch cập nhật miễn phí và hỗ trợ thương mại có SLA.
- Xác nhận đúng Alpine version, CPU architecture, tag JDK/JRE và native dependencies.
- Pin tag/digest, theo dõi security release và kiểm thử trong image production.
- Nếu native stack chỉ hỗ trợ glibc, hãy chọn image glibc được duy trì.

## Tài liệu tham khảo

- [Eclipse Temurin Docker Official Images](https://github.com/docker-library/docs/blob/master/eclipse-temurin/README.md) — tag Alpine cho JDK/JRE và biến thể image.
- [Temurin Support and Release Roadmap](https://adoptium.net/support) — hỗ trợ cộng đồng, hỗ trợ LTS và lịch phát hành.
- [Amazon Corretto Docker Official Image](https://hub.docker.com/_/amazoncorretto) — tag Alpine, biến thể JDK và kiến trúc được hỗ trợ.
- [Amazon Corretto FAQs and Support Calendar](https://aws.amazon.com/corretto/faqs/) — hỗ trợ musl trên Alpine và thời hạn LTS.
- [BellSoft Liberica JDK Containers](https://bell-sw.com/libericajdk-containers) — image Alpine/musl, registry và kiến trúc.
- [Liberica Alpine musl Docker tags](https://hub.docker.com/r/bellsoft/liberica-openjdk-alpine-musl/tags) — tag và bản cập nhật thực tế của repository musl.
