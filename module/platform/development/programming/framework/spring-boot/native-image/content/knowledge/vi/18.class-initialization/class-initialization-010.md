# Ưu tiên sửa phạm vi cụ thể thay vì áp đặt một chế độ cho mọi lớp

## 1. Vì sao cần điều chỉnh class initialization?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng **Spring AOT** rồi biên dịch thành GraalVM Native Image để đánh giá thời gian khởi động, bộ nhớ và khả năng tương thích. Một quyết định quan trọng khi tạo native executable là **khi nào class initializer của từng lớp được chạy**:

- **Build time:** static initializer chạy trong tiến trình tạo native image. Giá trị static được ghi nhận vào image heap và trở thành trạng thái ban đầu của executable.
- **Runtime:** static initializer chạy khi lớp được sử dụng lần đầu trong ứng dụng native.

Native Image có thể khởi tạo sớm một số lớp mà công cụ chứng minh là an toàn. Mặc định, các lớp ứng dụng còn lại thường được khởi tạo lúc runtime để giữ hành vi gần với JVM. Khi cần tối ưu hoặc sửa một lỗi tương thích, ta có thể chỉ định rõ phạm vi bằng:

- `--initialize-at-build-time=<class-or-package>`
- `--initialize-at-run-time=<class-or-package>`

Điểm cần nhớ là **một lớp cụ thể có thể cần chính sách khác với phần còn lại của ứng dụng**. Hãy tìm đúng lớp có static initializer không phù hợp, xác định dữ liệu mà initializer tạo ra, rồi điều chỉnh phạm vi nhỏ nhất có thể. Áp dụng một chế độ cho toàn bộ classpath có thể làm thay đổi hành vi của những thư viện vốn đang hoạt động đúng.

## 2. Class initialization diễn ra khi nào?

Theo ngữ nghĩa Java, một lớp được khởi tạo khi nó được sử dụng lần đầu theo những điều kiện của JVM. Việc nạp class không đồng nghĩa với việc chạy static initializer. Trình khởi tạo tĩnh thường được biên dịch thành method đặc biệt `<clinit>`.

Ví dụ:

~~~java
public final class RegionSettings {

    static final String REGION = System.getenv("APP_REGION");

    static {
        System.out.println("RegionSettings initialized");
    }

    private RegionSettings() {
    }
}
~~~

Khi class được khởi tạo, JVM đọc biến môi trường và chạy static block. Nếu Native Image quyết định hoặc được yêu cầu khởi tạo lớp này ở build time, giá trị APP_REGION được đọc từ môi trường máy build và trạng thái static được lưu vào image heap.

Nếu lớp được khởi tạo ở runtime, static initializer chạy trong môi trường của tiến trình native khi lớp được sử dụng lần đầu. Vì vậy, thay đổi môi trường triển khai có thể được phản ánh đúng.

### 2.1. Build time và runtime trong Native Image

~~~mermaid
flowchart TB
    S["Java bytecode + dependencies"] --> A["Native Image phân tích class initialization"]
    A --> B{"Lớp được khởi tạo ở thời điểm nào?"}
    B -->|Build time| C["Chạy <clinit> trong image builder"]
    C --> D["Ghi static state vào image heap"]
    D --> E["Native executable chứa trạng thái ban đầu"]
    B -->|Runtime| F["Đưa class initializer vào executable"]
    F --> G["Chạy <clinit> khi class được dùng lần đầu"]
    E --> H["Ứng dụng native chạy"]
    G --> H
~~~

Khi một lớp được khởi tạo ở build time, các đối tượng có thể truy cập từ static field của lớp đó được lưu vào image heap. Khi executable khởi động, image heap ban đầu được sử dụng làm trạng thái ban đầu của ứng dụng.

Điều này có thể giảm công việc khởi tạo và kiểm tra trạng thái lớp ở runtime. Tuy nhiên, nếu initializer tạo ra nhiều object hoặc cấu trúc dữ liệu lớn, image heap và kích thước binary có thể tăng. Lợi ích phải được đo trên ứng dụng thực tế.

## 3. Phân biệt Spring AOT với class initialization

Hai khái niệm này thường xuất hiện trong cùng một pipeline nhưng giải quyết hai việc khác nhau:

| Khái niệm | Thực hiện việc gì? | Ví dụ |
| --- | --- | --- |
| Spring AOT | Phân tích ApplicationContext và sinh mã/metadata phục vụ khởi động, binding và native image | Sinh mã đăng ký bean, runtime hints |
| Class initialization | Quyết định khi nào static initializer của từng Java class chạy | --initialize-at-build-time, --initialize-at-run-time |
| Native Image compilation | Phân tích bytecode, metadata và tạo executable | nativeCompile, native:compile |

Spring AOT không có nghĩa là mọi static initializer trong ứng dụng đều chạy ở build time. Ngược lại, chỉ thêm --initialize-at-build-time cũng không thay thế bước Spring AOT.

Khi điều tra lỗi, cần xác định lỗi nằm ở quá trình tạo ApplicationContext/AOT hay nằm trong <clinit> của một class. Không nên thay đổi class initialization policy chỉ để che một lỗi bean registration hoặc cấu hình Spring.

## 4. Lớp nào phù hợp với build-time initialization?

Build-time initialization phù hợp khi static initializer:

- chỉ thực hiện phép tính xác định từ dữ liệu cố định;
- tạo cấu trúc dữ liệu bất biến, nhỏ và dùng chung;
- không đọc môi trường của máy build;
- không phụ thuộc thời gian, locale, timezone, filesystem hoặc dịch vụ bên ngoài;
- không tạo trạng thái bảo mật hoặc trạng thái ngẫu nhiên cần riêng cho từng lần chạy.

Ví dụ một bảng tra cứu bất biến:

~~~java
import java.util.Map;

public final class CurrencyCatalog {

    static final Map<String, Integer> FRACTION_DIGITS = Map.of(
        "VND", 0,
        "USD", 2,
        "EUR", 2,
        "JPY", 0
    );

    private CurrencyCatalog() {
    }

    public static int fractionDigits(String currency) {
        return FRACTION_DIGITS.getOrDefault(currency, 2);
    }
}
~~~

Bảng này được tạo hoàn toàn từ dữ liệu cố định và Map.of tạo map không thể sửa đổi. Nếu class được khởi tạo ở build time, bảng tra cứu đã sẵn sàng trong image heap và không cần dựng lại lúc ứng dụng bắt đầu.

Có thể chỉ định một class cụ thể:

~~~bash
native-image \
  --initialize-at-build-time=com.example.billing.CurrencyCatalog \
  -jar target/billing-service.jar
~~~

Không cần chỉ định cả package com.example.billing nếu chỉ CurrencyCatalog có initializer phù hợp. Nếu package có thêm lớp đọc database, locale hoặc cấu hình runtime, phạm vi package sẽ quá rộng.

## 5. Lớp nào nên khởi tạo ở runtime?

Nên giữ class initialization ở runtime nếu static initializer phụ thuộc vào dữ liệu chỉ có ý nghĩa trong môi trường chạy hoặc tạo trạng thái phải mới cho từng tiến trình.

Những ví dụ thường gặp:

| Nội dung trong static initializer | Vì sao cần runtime? |
| --- | --- |
| Đọc System.getenv() hoặc System.getProperty() | Mỗi môi trường triển khai có giá trị khác nhau |
| Lấy ZoneId.systemDefault() hoặc Locale.getDefault() | Phụ thuộc cấu hình hệ điều hành của môi trường chạy |
| Đọc file, thư mục tạm hoặc biến đường dẫn | Máy build và container runtime có filesystem khác nhau |
| Tạo SecureRandom hoặc seed ngẫu nhiên | Trạng thái ngẫu nhiên không nên được chụp từ môi trường build |
| Khởi tạo crypto provider hoặc native library | Có thể phụ thuộc nền tảng, provider và môi trường runtime |
| Tạo thread, executor hoặc thread-local state | Đây là tài nguyên của tiến trình đang chạy |
| Mở socket, kết nối database hoặc gọi HTTP | Không nên thực hiện trong image builder |
| Đọc credential hoặc secret | Có nguy cơ lưu dữ liệu nhạy cảm vào image heap/binary |

Ví dụ lớp đọc vùng triển khai:

~~~java
public final class RegionSettings {

    static final String REGION = System.getenv("APP_REGION");

    private RegionSettings() {
    }

    public static String region() {
        return REGION;
    }
}
~~~

Nếu lớp trên được khởi tạo ở build time, giá trị vùng của máy build có thể bị giữ trong binary. Có thể yêu cầu khởi tạo class này ở runtime:

~~~bash
native-image \
  --initialize-at-run-time=com.example.runtime.RegionSettings \
  -jar target/billing-service.jar
~~~

Tốt hơn nữa, nếu dữ liệu vốn là cấu hình ứng dụng như region, endpoint hay timeout, hãy cân nhắc đưa nó vào Spring @ConfigurationProperties và inject vào bean lúc runtime. Tránh dùng static mutable state làm kho cấu hình toàn cục.

## 6. Vì sao không nên áp dụng một chế độ cho toàn bộ classpath?

### 6.1. Ép tất cả khởi tạo ở build time

Một tùy chọn build-time ở phạm vi toàn cục có thể khiến static initializer của thư viện bên thứ ba chạy trong máy build. Khi đó:

- môi trường, timezone hoặc system property của máy build có thể bị ghi vào image heap;
- seed ngẫu nhiên, credential hoặc thông tin hệ thống có thể bị giữ trong binary;
- initializer có thể mở file, tạo thread hoặc thực hiện thao tác không phù hợp với image builder;
- cấu trúc dữ liệu lớn được tạo trước có thể làm image heap tăng;
- thư viện có giả định về runtime có thể hoạt động sai hoặc khiến build thất bại.

Native Image tự phân tích để khởi tạo build time những lớp được chứng minh là an toàn. Không nên thay cơ chế đó bằng một quy tắc ép toàn bộ classpath.

### 6.2. Ép tất cả khởi tạo ở runtime

Ngược lại, ép mọi lớp về runtime có thể:

- tăng số class initializer phải chạy khi ứng dụng sử dụng các lớp lần đầu;
- tăng chi phí kiểm tra trạng thái khởi tạo trước khi truy cập static field/method;
- bỏ qua cơ hội chuẩn bị trước các bảng tra cứu và cấu trúc dữ liệu bất biến;
- gây xung đột với object đã được tạo trong image heap nếu object thuộc class bị yêu cầu khởi tạo runtime.

Runtime initialization cũng có ràng buộc: **không được có instance của class cần khởi tạo runtime nằm sẵn trong image heap**, vì instance đó sẽ tồn tại trước khi class được khởi tạo theo ngữ nghĩa Java.

### 6.3. Cách chọn phạm vi

| Tình huống | Cách xử lý |
| --- | --- |
| Một class đọc environment trong static initializer | Đưa riêng class đó về runtime hoặc chuyển đọc cấu hình vào bean/runtime accessor |
| Một class tạo bảng tra cứu bất biến từ dữ liệu cố định | Cân nhắc build-time cho đúng class |
| Cả package chứa nhiều loại class khác nhau | Không áp dụng policy cho cả package; tách class cần điều chỉnh |
| Lỗi phát sinh từ thư viện bên thứ ba | Xác định class initializer cụ thể và đọc hướng dẫn tương thích của thư viện |
| Không biết class nào chạy ở build time | Bật diagnostic class initialization và trace class cụ thể |

## 7. Cấu hình theo class hoặc package

Native Image cung cấp hai tùy chọn chính:

~~~bash
--initialize-at-build-time=com.example.catalog.CurrencyCatalog
--initialize-at-run-time=com.example.runtime.RegionSettings
~~~

Có thể chỉ định nhiều class bằng danh sách phân tách dấu phẩy:

~~~bash
--initialize-at-run-time=com.example.runtime.RegionSettings,com.example.crypto.ProviderBootstrap
~~~

Cũng có thể chỉ định package:

~~~bash
--initialize-at-run-time=com.example.legacy
~~~

Policy package áp dụng cho phạm vi rộng hơn và có thể bao gồm các lớp mới được thêm vào package trong tương lai. Một class mới có static initializer khác biệt có thể vô tình nhận policy không phù hợp. Vì vậy, hãy ưu tiên class cụ thể; chỉ dùng package khi toàn bộ package có cùng yêu cầu và đã được kiểm tra.

### 7.1. Ràng buộc của hệ phân cấp lớp

Java class initialization chịu ảnh hưởng của superclass và interface có default method:

- Khi class được khởi tạo, các relevant superclass và superinterface có default method phải được khởi tạo theo quy tắc Java.
- Relevant supertype của class được khởi tạo ở build time cũng phải được khởi tạo ở build time.
- Relevant subtype của class được khởi tạo ở runtime cũng phải được khởi tạo ở runtime.
- Class được yêu cầu khởi tạo runtime không được có instance nằm trong image heap.

Do đó, một thay đổi policy cho một class có thể làm Native Image yêu cầu điều chỉnh thêm các class liên quan. Hãy đọc thông báo build và xử lý theo hệ phân cấp thực tế; không mở rộng policy cho toàn package chỉ để làm biến mất thông báo lỗi.

## 8. Ví dụ Spring Boot: tách dữ liệu cố định khỏi cấu hình runtime

Giả sử ứng dụng có bảng tra cứu mã tiền tệ và cấu hình region:

~~~java
public final class CurrencyCatalog {
    static final Map<String, Integer> FRACTION_DIGITS = Map.of(
        "VND", 0,
        "USD", 2,
        "EUR", 2
    );

    private CurrencyCatalog() {
    }
}
~~~

Đây là dữ liệu cố định, có thể phù hợp để khởi tạo ở build time nếu không có dependency runtime khác.

Với region, nên dùng cấu hình Spring:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.region")
public record RegionProperties(String name) {
}
~~~

Đăng ký properties bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties, sau đó inject vào bean cần dùng. Giá trị có thể được cung cấp ở runtime:

~~~yaml
app:
  region:
    name: ap-southeast-1
~~~

Trong môi trường khác, override bằng environment variable:

~~~bash
APP_REGION_NAME=ap-southeast-2 ./target/billing-service
~~~

Không cần ép RegionProperties hoặc toàn bộ package cấu hình về build time. Spring Binder đọc property source khi ứng dụng native khởi động; class initialization policy là một cơ chế riêng.

## 9. Đưa policy vào Maven và Gradle

### 9.1. Maven Native Build Tools

Có thể truyền Native Image arguments qua cấu hình plugin native-maven-plugin. Ví dụ:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--initialize-at-run-time=com.example.runtime.RegionSettings</buildArg>
            <buildArg>--initialize-at-build-time=com.example.catalog.CurrencyCatalog</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Đặt cấu hình trong module ứng dụng tạo native executable. Nếu project dùng Spring Boot Parent hoặc parent nội bộ, kiểm tra effective POM để tránh khai báo trùng hoặc bị cấu hình parent ghi đè. Tên plugin và DSL có thể khác theo version; đối chiếu Native Build Tools version đang dùng.

### 9.2. Gradle Native Build Tools

Ví dụ với Kotlin DSL trong build.gradle.kts:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add(
                "--initialize-at-run-time=com.example.runtime.RegionSettings"
            )
            buildArgs.add(
                "--initialize-at-build-time=com.example.catalog.CurrencyCatalog"
            )
        }
    }
}
~~~

Các argument được gắn vào binary main. Với Groovy DSL hoặc version plugin khác, cú pháp container có thể khác; kiểm tra cấu hình plugin của dự án trước khi copy nguyên đoạn này.

Sau khi thay đổi policy, cần build lại native executable. Chỉ thay đổi environment khi chạy binary không thể thay đổi class initialization policy đã được biên dịch vào executable.

## 10. Chẩn đoán class initialization

Khi build lỗi hoặc ứng dụng có hành vi khác JVM, đừng đoán class nào cần đổi policy. Hãy thu thập bằng chứng trước.

### 10.1. In danh sách và lý do khởi tạo lớp

Có thể bật diagnostic:

~~~bash
native-image -H:+PrintClassInitialization -jar target/billing-service.jar
~~~

Tùy phiên bản GraalVM, option này in thông tin các lớp được khởi tạo ở build time và lý do/nhóm phân loại liên quan. Output có thể dài; hãy lọc theo package hoặc class đang điều tra. Kiểm tra option trên bản GraalVM cài đặt bằng `native-image --help-extra` hoặc `native-image --expert-options`.

### 10.2. Trace một class cụ thể

Nếu nghi ngờ một class:

~~~bash
native-image \
  --trace-class-initialization=com.example.runtime.RegionSettings \
  -jar target/billing-service.jar
~~~

Trace giúp xác định class được khởi tạo ở đâu trong quá trình build. Option và mức chi tiết có thể khác theo phiên bản GraalVM; kiểm tra `native-image --help`/`--help-extra` nếu bản cài không nhận tham số.

### 10.3. Đọc static initializer

Sau khi xác định class:

1. Mở static field initializer và static block của class.
2. Theo dõi các method được gọi trực tiếp hoặc gián tiếp.
3. Tìm thao tác đọc environment, system property, file, clock, locale, timezone, random hoặc tài nguyên hệ thống.
4. Kiểm tra object được tạo có thể đi vào image heap không.
5. Kiểm tra superclass, interface có default method và subtype liên quan.
6. Chọn policy nhỏ nhất rồi build lại.

Không phải mọi lỗi UnsupportedFeatureError đều là lỗi class initialization. Nếu lỗi liên quan reflection, JNI, resource hoặc proxy, hãy xử lý đúng loại metadata thay vì đổi policy lớp.

## 11. Quy trình sửa lỗi theo phạm vi cụ thể

Giả sử native image ghi nhận RegionSettings đã được khởi tạo ở build time và executable luôn dùng region của máy CI.

**Bước 1 — xác nhận nguyên nhân**

Kiểm tra static initializer:

~~~java
static final String REGION = System.getenv("APP_REGION");
~~~

Đây là giá trị môi trường được chụp khi class được khởi tạo.

**Bước 2 — ưu tiên sửa thiết kế**

Nếu đây là cấu hình ứng dụng, chuyển sang Spring @ConfigurationProperties và inject bean. Nếu cần API tĩnh vì lý do tương thích, ít nhất hãy đọc giá trị trong method chạy ở runtime thay vì lưu trong static initializer:

~~~java
public final class RegionSettings {
    private RegionSettings() {
    }

    public static String region() {
        return System.getenv("APP_REGION");
    }
}
~~~

**Bước 3 — nếu chưa thể sửa code, chỉ định runtime cho class đó**

~~~bash
native-image \
  --initialize-at-run-time=com.example.runtime.RegionSettings \
  -jar target/billing-service.jar
~~~

Không chuyển toàn bộ package com.example sang runtime chỉ vì một class đọc environment.

**Bước 4 — kiểm thử bằng môi trường khác máy build**

Build image với một giá trị APP_REGION, sau đó chạy executable với giá trị khác. Kết quả phải phản ánh cấu hình runtime mong muốn.

**Bước 5 — đo lại**

So sánh startup, RSS, thời gian build và hành vi của luồng nghiệp vụ trước/sau thay đổi. Runtime initialization có thể thêm chi phí ở lần sử dụng đầu tiên của class; xác nhận chi phí đó có ý nghĩa với ứng dụng hay không.

## 12. Kiểm thử class initialization

Một bộ test nên kiểm tra cả tính đúng đắn và tác động hiệu năng:

| Kiểm thử | Cách thực hiện | Điều cần xác nhận |
| --- | --- | --- |
| Environment isolation | Build với biến môi trường A, chạy với B | Binary không giữ giá trị A nếu dữ liệu phải đọc lúc runtime |
| Timezone/locale | Build và chạy với timezone/locale khác nhau | Kết quả theo môi trường chạy khi yêu cầu nghiệp vụ là runtime |
| Static immutable data | So sánh kết quả tra cứu trên JVM và native | Dữ liệu cố định giống nhau |
| Random/security | Khởi động nhiều tiến trình native | Seed/trạng thái bảo mật được tạo đúng lúc và không bị dùng chung từ build |
| External resources | Chạy trong container với filesystem/network runtime | Không có I/O ngoài ý muốn ở build time |
| Class hierarchy | Build sau khi thay policy một class | Không vi phạm ràng buộc superclass/subtype hoặc image heap |
| Startup/footprint | Đo cùng workload trước và sau | Thay đổi policy có lợi ích đo được và không gây lỗi |

Nên test executable trong ít nhất hai môi trường cấu hình khác nhau. Test JVM đơn thuần không thể xác nhận static state nào đã được chụp vào image heap.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Native luôn dùng giá trị environment của CI | Class chứa System.getenv() được khởi tạo ở build time | Chuyển đọc cấu hình về runtime hoặc chỉ định class đó bằng --initialize-at-run-time |
| Build lỗi khi ép package build time | Có class trong package thực hiện thao tác không an toàn | Xác định class cụ thể; bỏ policy package và cấu hình theo từng class |
| Image heap chứa instance của class runtime | Một object thuộc class runtime đã được tạo ở build time | Tìm đường tạo object, chuyển việc tạo về runtime hoặc điều chỉnh policy liên quan |
| Policy class bị ảnh hưởng bởi superclass | Ràng buộc Java class initialization | Kiểm tra relevant supertype và điều chỉnh phạm vi liên quan |
| Native khởi động chậm hơn sau khi chuyển nhiều class sang runtime | Nhiều initializer và kiểm tra class state chạy ở runtime | Thu hẹp danh sách runtime, chỉ giữ các class cần môi trường runtime |
| Binary lớn hơn sau khi bật build time | Initializer tạo nhiều object được lưu trong image heap | Thu hẹp class, giảm dữ liệu tĩnh hoặc khởi tạo dữ liệu lớn ở runtime |
| Không nhận option diagnostic | Khác biệt giữa GraalVM versions | Kiểm tra native-image --help, --help-extra và tài liệu đúng version |
| Spring AOT vẫn lỗi sau khi đổi class policy | Lỗi thuộc ApplicationContext/AOT chứ không phải <clinit> | Kiểm tra bean conditions, generated code và runtime hints |

## 14. Checklist trước khi phát hành

- [ ] Đã xác định class initializer gây vấn đề bằng log/trace, không đoán theo package.
- [ ] Đã đọc static initializer và các lời gọi gián tiếp của class.
- [ ] Đã phân biệt dữ liệu cố định với dữ liệu phụ thuộc môi trường chạy.
- [ ] Không đưa credential, random seed hoặc dữ liệu hệ thống vào image heap từ build time.
- [ ] Chỉ dùng --initialize-at-build-time cho class có initializer xác định, an toàn và cần tối ưu.
- [ ] Chỉ dùng --initialize-at-run-time cho class cần trạng thái runtime.
- [ ] Không áp dụng policy package rộng khi chỉ một class cần thay đổi.
- [ ] Đã kiểm tra ràng buộc superclass/subtype và object trong image heap.
- [ ] Đã kiểm thử với environment/timezone/locale khác máy build.
- [ ] Đã đo startup, RSS, kích thước image và thời gian build sau thay đổi.
- [ ] Đã xác nhận policy trong đúng Maven/Gradle native build configuration.

**Ghi nhớ:** Native Image mặc định giữ runtime initialization cho các class ứng dụng mà nó không chứng minh an toàn để khởi tạo sớm. Build-time initialization có thể giảm công việc lúc chạy nhưng cũng chụp static state vào image heap. Khi gặp lỗi, hãy tìm class initializer cụ thể, phân biệt trạng thái cố định và trạng thái môi trường, rồi điều chỉnh class nhỏ nhất có thể. Chỉ mở rộng sang package khi tất cả class trong phạm vi đó thực sự cần cùng một policy.

## Tài liệu tham khảo

- [GraalVM — Specify Class Initialization Explicitly](https://www.graalvm.org/latest/reference-manual/native-image/guides/specify-class-initialization/): cú pháp --initialize-at-build-time, --initialize-at-run-time và ví dụ theo class/package.
- [GraalVM — Class Initialization in Native Image](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/ClassInitialization/): mặc định, safe class initialization, image heap và các ràng buộc của hệ phân cấp lớp.
- [GraalVM — Native Image Basics](https://www.graalvm.org/latest/reference-manual/native-image/basics/): phân biệt build time/runtime và static state được lưu trong image heap.
- [GraalVM — Security Considerations in Native Image](https://www.graalvm.org/dev/security-guide/native-image/): rủi ro dữ liệu nhạy cảm và random state khi static initializer chạy ở build time.
- [GraalVM — Native Image Command-line Options](https://www.graalvm.org/reference-manual/native-image/Options/): cách kiểm tra các option được hỗ trợ theo phiên bản GraalVM.
