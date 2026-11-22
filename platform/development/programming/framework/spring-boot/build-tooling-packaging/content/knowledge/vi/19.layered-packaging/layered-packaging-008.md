# Nhận diện khác biệt giữa jarmode tools và layertools ở các phiên bản Spring Boot

## 1. Vì sao phải phân biệt phiên bản khi trích xuất lớp JAR?

Một Dockerfile lấy từ dự án Spring Boot 3.2 có thể chứa lệnh:

```bash
java -Djarmode=layertools -jar application.jar extract
```

Khi nâng lên Spring Boot 3.5 hoặc 4.1, không nên giữ nguyên cú pháp chỉ vì executable JAR vẫn có `BOOT-INF/layers.idx`. Spring Boot đã thay đổi **JAR mode tích hợp**, **tên các lệnh con**, **kiểu thư mục khi giải nén**, **dependency JAR hỗ trợ** và **cấu hình build plugin**.

Hai tên cần phân biệt:

- **`layertools`**: JAR mode cũ dựa trên artifact `spring-boot-jarmode-layertools`; phổ biến từ khi layered JAR được hỗ trợ trong Spring Boot 2.3 đến dòng 3.2.
- **`tools`**: JAR mode mới dựa trên artifact `spring-boot-jarmode-tools`, xuất hiện trong Spring Boot **3.3**, hỗ trợ trích xuất **theo layers** và **layout đã giải nén tối ưu hơn cho chạy ứng dụng/CDS**.

**Kết luận thực hành:** với Boot **3.3 trở lên**, ưu tiên `-Djarmode=tools`. Nếu cần tái tạo cách `layertools extract` cũ (bốn thư mục layer phục vụ Docker COPY), lệnh mới phải có **`extract --layers`**. Đừng nhầm nó với `tools extract` **không có `--layers`**, vì chế độ mặc định tạo một cấu trúc thư mục khác.

Bài học dùng Java 17 và ví dụ Spring Boot 3.5.16 để thực hành, đồng thời trình bày rõ cách xử lý artifact Boot 3.2 và mốc loại bỏ ở 4.1. Đây là các **phiên bản minh họa đã pin**, không phải gợi ý thay đổi bản phát hành mà dự án đang dùng nếu chưa kiểm tra compatibility.

### Kết quả sau bài học

1. Nhìn một Dockerfile hoặc CI script và nhận biết nó đang dùng `layertools` hay `tools`.
2. So sánh được Boot **2.3–3.2**, **3.3–4.0** và **4.1+** về tên JAR mode, commands, dependency và trạng thái hỗ trợ.
3. Phân biệt `layers.idx`, `classpath.idx`, nested dependencies và tool JAR.
4. Chạy đúng `list`/`list-layers`, `extract`/`extract --layers`, `help` theo **phiên bản artifact**.
5. Biết cấu hình `includeLayerTools` cũ và `includeTools` mới trên Maven/Gradle, độc lập với việc bật/tắt sinh `layers.idx`.
6. Đóng gói một executable Spring Boot JAR Java 17, xem archive, trích layers và chạy ứng dụng từ cả JAR gốc và cấu trúc đã trích xuất.
7. Chuyển Dockerfile sang cấu trúc mới mà không copy nhầm entrypoint của loader cũ.
8. Nhận diện lỗi khi tool JAR bị loại, layers index thiếu hoặc archive có launch script (fully executable JAR).

## 2. Mốc thay đổi theo phiên bản Spring Boot

| Dòng phiên bản | JAR mode nên dùng | Commands cơ bản | Tool JAR / cấu hình |
|---|---|---|---|
| **Boot 2.3 đến 3.2.x** | `layertools` | `list`, `extract`, `help` | `spring-boot-jarmode-layertools`, `layers.includeLayerTools` |
| **Boot 3.3.x** | **`tools`**; `layertools` bị deprecated | `list-layers`, `extract`, `help` | `spring-boot-jarmode-tools`, `includeTools` |
| **Boot 3.4.x – 3.5.x** | **`tools`** | `list-layers`, `extract`, `help` | `includeTools` của Maven/Gradle packaging |
| **Boot 4.0.x** | **`tools`** | `list-layers`, `extract`, `help` | Dùng cấu hình mới, tránh dependency vào cú pháp legacy |
| **Boot 4.1.x trở lên** | **`tools`** | `list-layers`, `extract`, `help` | `layertools` **đã bị loại bỏ** trong 4.1 |

Mốc lịch sử đã được công bố chính thức:

- Spring Boot **2.3** bổ sung layered JAR cho Docker/OCI image và JAR mode `layertools`.
- Spring Boot **3.3** giới thiệu `tools` cùng chế độ trích xuất tối ưu cho **Class Data Sharing (CDS)**; chuyển các thao tác `layertools` cũ sang lệnh mới, đồng thời deprecate giao diện cũ.
- Spring Boot **4.1** loại bỏ `layertools` đã deprecated. Khi dự án chạy Boot 4.1, lệnh `-Djarmode=layertools` **không còn là phương án được hỗ trợ**, cần chuyển sang `tools`.

**Phân biệt “deprecated” và “removed”:** 3.3 thông báo không nên dùng giao diện cũ; 4.1 loại bỏ hẳn giao diện đó. Với artifact 3.3–4.0, **không mặc định** cho rằng JAR đã đóng gói kèm cả hai tool JAR hoặc mọi lệnh cũ vẫn chạy. Xem `BOOT-INF/lib` và thử chính artifact build ra để biết khả năng thực tế. Dùng cú pháp mới là cách ổn định nhất cho Dockerfile/CI lâu dài.

### Ma trận chuyển đổi lệnh quan trọng nhất

| Mục đích | Legacy `layertools` (Boot 3.2) | `tools` (Boot 3.3+) |
|---|---|---|
| In danh sách thao tác | `java -Djarmode=layertools -jar app.jar` | `java -Djarmode=tools -jar app.jar` |
| Xem các layer | `java -Djarmode=layertools -jar app.jar list` | `java -Djarmode=tools -jar app.jar list-layers` |
| Trích theo layer | `java -Djarmode=layertools -jar app.jar extract` | `java -Djarmode=tools -jar app.jar extract --layers --destination extracted` |
| Trợ giúp | `java -Djarmode=layertools -jar app.jar help` | `java -Djarmode=tools -jar app.jar help extract` |
| Trích theo **layout mới** tối ưu chạy | Không phải tính năng `layertools extract` kiểu cũ | `java -Djarmode=tools -jar app.jar extract` |
| Loại tool JAR khỏi build | `layers.includeLayerTools=false` | `includeTools=false` |

**Không thay `list` thành `list-layers` khi vẫn dùng `-Djarmode=layertools`; cũng không dùng `list` của layertools trong `tools`.** Lệnh được parse bởi đúng implementation của JAR mode đã đóng gói, không phải bởi Java launcher.

## 3. Ba khái niệm hay bị đánh đồng

### 3.1. BOOT-INF/layers.idx — chỉ mục phân lớp image

Layered JAR vẫn có cấu trúc executable Spring Boot bình thường:

```text
layer-lab-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/com/example/layerlab/LayerLabApplication.class
    ├── lib/
    │   ├── spring-boot-3.5.16.jar
    │   ├── spring-boot-jarmode-tools-3.5.16.jar
    │   └── ... các dependency runtime khác
    ├── layers.idx
    └── classpath.idx             (nếu được tạo)
```

Sơ đồ trên là **minh họa**, không cam kết một build có đúng mọi entry/phiên bản dependency. Khi `includeTools=false`, sẽ không có tool JAR tương ứng. Khi tắt layers, `layers.idx` có thể không có.

`BOOT-INF/layers.idx` mô tả **thành phần file/JAR thuộc Docker/OCI layer nào** và thứ tự các layers để tối ưu cache. Theo cấu hình mặc định thông dụng:

| Layer | Thường chứa | Lý do |
|---|---|---|
| `dependencies` | Dependency release không có `SNAPSHOT` | Ít thay đổi, tận dụng cache |
| `spring-boot-loader` | Các class Loader | Thường thay đổi khi nâng Boot |
| `snapshot-dependencies` | Dependency có phiên bản `SNAPSHOT` | Dễ thay đổi trong phát triển |
| `application` | Class/resources ứng dụng và local module dependencies | Thay đổi thường xuyên |

Thứ tự layer thường là:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

Ví dụ **rút gọn** nội dung index (không phải toàn văn file thật):

```yaml
- "dependencies":
  - "BOOT-INF/lib/spring-core-6.x.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/"
- "snapshot-dependencies":
  - "BOOT-INF/lib/example-client-1.0-SNAPSHOT.jar"
- "application":
  - "BOOT-INF/classes/"
```

Mỗi entry tương ứng đường dẫn trong archive. Tên JAR/version trong ví dụ chỉ có tác dụng minh họa, không được dùng như file path literal để copy trong script.

**Index này có thể vẫn tồn tại dù bạn tắt việc đóng kèm tool JAR.** Thao tác `includeTools=false` và `layers.enabled=false` không đồng nghĩa: một cái điều khiển **đóng kèm công cụ trích xuất**, một cái điều khiển **sinh thông tin phân lớp**.

### 3.2. BOOT-INF/classpath.idx — thứ tự classpath

`BOOT-INF/classpath.idx` liệt kê các nested JAR được đưa vào **classpath theo thứ tự**, phục vụ Boot Loader khi chạy executable archive. Nó không quyết định Docker layer và không có cùng cú pháp/ý nghĩa với `layers.idx`.

| File | Ý nghĩa | Có phải điều kiện duy nhất để dùng jarmode? |
|---|---|---|
| `BOOT-INF/layers.idx` | Mô tả layers để công cụ liệt kê/trích theo lớp | Cần layer metadata cho thao tác theo layers |
| `BOOT-INF/classpath.idx` | Thứ tự nested JAR trên application classpath | **Không** phải layer metadata |
| `BOOT-INF/lib/spring-boot-jarmode-*.jar` | Mã của jarmode implementation được Boot đóng kèm | Cần đúng implementation, đúng mode |
| `META-INF/MANIFEST.MF` | Launcher/main bootstrap của archive | Cần một executable archive phù hợp |

Đừng sửa `classpath.idx` để cố đổi Docker layer order, cũng đừng sửa `layers.idx` để khắc phục `NoSuchMethodError` do dependency conflict. Hai loại metadata giải quyết hai vấn đề khác nhau.

### 3.3. Docker layers khác classpath và Maven/Gradle layers

Một `Dockerfile` nhiều lệnh `COPY` tạo nhiều image layers. Mỗi `COPY` thường lấy nội dung từ một thư mục do jarmode tạo ra, ví dụ `extracted/dependencies/`. Không phải JVM sẽ đọc `dependencies` trước rồi nạp tất cả class trong `application` cuối cùng; JVM nạp class theo nhu cầu và classloader.

Layering tối ưu **khả năng dùng lại cache** khi ứng dụng thay đổi, không đảm bảo một image luôn nhỏ hơn hay thời gian chạy chắc chắn nhanh hơn. Kết quả tùy Docker cache policy, số lượng dependency, kích thước artifact và cách build image.

## 4. JAR mode được kích hoạt ở đâu?

Cú pháp Java launcher:

```text
java [JVM options] -jar application.jar [arguments for jar mode]
     └─ -Djarmode=tools ─┘            └─ extract --layers ...
```

`-Djarmode=tools` là **Java system property**, cần đứng **trước `-jar`** để được Java launcher chuyển đến JVM. `extract` và `--layers` là các đối số của chế độ tools, đứng **sau tên archive**.

Đúng:

```bash
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar list-layers
```

Sai cách đặt flag:

```bash
java -jar target/layer-lab-0.0.1-SNAPSHOT.jar -Djarmode=tools list-layers
```

Lệnh sai chuyển các chuỗi này cho **main ứng dụng** dưới dạng application arguments, không bảo đảm bật JAR mode. Nó có thể chạy app bình thường thay vì in layers.

**JAR mode không phải Maven profile hoặc Spring profile.** `-Pproduction` của Maven, `--spring.profiles.active=prod` của Spring Boot và `-Djarmode=tools` là ba cơ chế khác nhau. Tool mode chủ yếu phục vụ **inspect/extract archive**, không chạy logic web/controller/CommandLineRunner của ứng dụng.

Một vài lưu ý:

- Java version phải phù hợp bytecode và Spring Boot version của executable archive.
- `java -Djarmode=tools -jar ...` là lệnh **chạy archive đã đóng gói**, không phải `mvn spring-boot:run` hoặc `gradle bootRun`.
- Nếu archive dùng launch script được chèn đầu file kiểu **fully executable**, tài liệu Spring Boot cảnh báo tools/layertools không hỗ trợ đường trích xuất này; hãy build archive thông thường nếu dự định dùng `extract`.
- Không tự giả định một plain `jar` hay một file `*-plain.jar` có Loader/`layers.idx`/tool JAR; phải chọn đúng `bootJar` hoặc Maven repackage output.

## 5. Chi tiết layertools (Boot 2.3–3.2)

### 5.1. Tên mode và các commands

Với executable JAR **được build bằng Spring Boot 3.2.12** và có `spring-boot-jarmode-layertools`:

```bash
# Liệt kê các thao tác:
java -Djarmode=layertools -jar target/layer-lab-0.0.1-SNAPSHOT.jar

# Liệt kê layer:
java -Djarmode=layertools -jar target/layer-lab-0.0.1-SNAPSHOT.jar list

# Trích xuất theo các thư mục layer ở working directory:
java -Djarmode=layertools -jar target/layer-lab-0.0.1-SNAPSHOT.jar extract
```

Các command hỗ trợ: `list`, `extract` và `help`. `list-layers` là **lệnh mới của tools**, không phải tên command chuẩn của layertools 3.2.

Kết quả `list` thông thường gồm các tên layer như:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

Đây là **danh sách layer mặc định** trong ví dụ, không cam kết mọi project có cùng layers: build cấu hình custom `layers.xml` có thể đổi tên và thứ tự.

### 5.2. Đường dẫn kết quả layertools extract

Thực hiện ở một working directory riêng để không trộn với source/build:

```bash
mkdir -p legacy-out
cd legacy-out
java -Djarmode=layertools -jar ../target/layer-lab-0.0.1-SNAPSHOT.jar extract
cd ..
```

Sau khi extract thành công, thư mục `legacy-out/` thường chứa:

```text
legacy-out/
├── dependencies/
│   └── BOOT-INF/lib/...
├── spring-boot-loader/
│   └── org/springframework/boot/loader/...
├── snapshot-dependencies/
│   └── BOOT-INF/lib/...      (nếu có SNAPSHOT dependencies)
└── application/
    ├── BOOT-INF/classes/...
    └── META-INF/MANIFEST.MF
```

Đó là **bố trí phù hợp để Dockerfile copy lần lượt các thư mục layer** vào cùng `WORKDIR`. Trường hợp không có dữ liệu ở một layer, output thực tế tùy tool, nhưng layer name vẫn nên dựa trên `layers.idx` của artifact, không đoán từ Dockerfile đã copy.

Spring Boot 3.2 Dockerfile mẫu thường khởi chạy bằng:

```dockerfile
ENTRYPOINT ["java", "org.springframework.boot.loader.launch.JarLauncher"]
```

Đây là **main class của Boot Loader 3.2** khi nội dung được unpack ra classpath, **không phải cách khởi chạy tối ưu mặc định của tools 3.3+**. Nếu bạn đang nâng Dockerfile, phải đánh giá **cả phần trích xuất và ENTRYPOINT**, không chỉ đổi `layertools` thành `tools`.

### 5.3. Tắt layer tools ở phiên bản cũ

Đoạn Maven plugin trong Boot 3.2:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layers>
            <includeLayerTools>false</includeLayerTools>
        </layers>
    </configuration>
</plugin>
```

Đây là **đoạn chèn dưới `<build><plugins>`**, không phải POM độc lập. Khi tắt inclusion, archive có thể **vẫn có `layers.idx`** nếu layering enabled, nhưng thiếu JAR mode implementation nên `java -Djarmode=layertools ...` không hoạt động.

Tương đương Gradle 3.2 Groovy DSL:

```groovy
tasks.named("bootJar") {
    layered {
        includeLayerTools = false
    }
}
```

**Không dùng** cấu hình `<includeTools>false</includeTools>` của 3.3+ để thay thế mù quáng trong POM 3.2 vì đó là tham số có mốc bổ sung khác. Khi cần kiểm tra project cũ, đọc **tài liệu plugin của chính dòng 3.2**.

## 6. Chi tiết tools (Boot 3.3, 3.4, 3.5, 4.0 và 4.1)

### 6.1. Liệt kê mode và layers

Với Spring Boot **3.5.16**, sau khi package executable JAR:

```bash
# Xem lệnh được tools hỗ trợ:
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar

# Xem tên các layer:
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar list-layers

# Xem chi tiết tham số trích xuất:
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar help extract
```

Những commands cơ bản của tools: `extract`, `list-layers`, `help`. Với project có custom layer names, kết quả `list-layers` phản ánh file `layers.idx` của **artifact đang kiểm tra**, không nhất thiết là bốn layer mặc định.

### 6.2. Có hai cách extract với layout khác nhau

**Cách A — extract mặc định, hướng tới chạy nhanh/CDS-friendly:**

```bash
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar extract
```

Nếu tên JAR là `layer-lab-0.0.1-SNAPSHOT.jar` và không đổi các tham số, kết quả thường có dạng:

```text
layer-lab-0.0.1-SNAPSHOT/
├── layer-lab-0.0.1-SNAPSHOT.jar
└── lib/
    └── ... các JAR dependency
```

Thư mục được đặt theo tên executable JAR bỏ phần mở rộng. File JAR **trong thư mục đã extract không phải uber JAR gốc**; nó chứa application classes/manifest và tham chiếu các thư viện đã giải nén ở `lib/`. Do đó có thể chạy:

```bash
java -jar layer-lab-0.0.1-SNAPSHOT/layer-lab-0.0.1-SNAPSHOT.jar
```

Đây là bố trí `tools extract` mặc định được Spring Boot 3.3 giới thiệu để giảm overhead nested JAR và hỗ trợ các kỹ thuật như CDS. **Không nhầm đường dẫn này với `extracted/application/BOOT-INF/classes` của layertools.**

**Cách B — extract theo layers phục vụ Docker COPY/caching:**

```bash
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar \
  extract --layers --destination extracted
```

Khi chạy từ thư mục gốc trên Linux/macOS, tool tạo dưới `extracted/` các layer directories:

```text
extracted/
├── dependencies/
├── spring-boot-loader/
├── snapshot-dependencies/
└── application/
```

Trong mỗi layer là các thư mục con của nội dung executable archive tương ứng, có thể ghép lại khi copy lần lượt vào thư mục runtime. **Điểm tương đương với layertools cũ là `extract --layers`, không phải `extract` thuần.**

Windows PowerShell có thể dùng **một dòng lệnh** để tránh khác cú pháp nối dòng Bash:

```powershell
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar extract --layers --destination extracted
```

Khi destination đã có nội dung, tools có thể từ chối ghi để bảo vệ dữ liệu; đọc `help extract` của đúng bản để biết cờ như `--force` nếu cần. Để bài học dễ tái lập, chọn thư mục trống hoặc xóa **đúng thư mục do mình tạo** sau khi xác nhận đường dẫn, không bật force trong pipeline một cách tùy tiện.

### 6.3. Vì sao tools không chỉ là tên mới?

Khi dùng `tools extract` **không có `--layers`**, ứng dụng được tạo theo layout có JAR nhỏ và `lib/`, có thể chạy bằng `java -jar extracted-app.jar`; layout này hữu ích cho Class Data Sharing/trình khởi động đã giải nén.

Khi dùng `tools extract --layers`, bạn nhận **một thư mục cho mỗi layer của image** để Dockerfile có thể `COPY` từng phần. Cấu trúc hướng về image caching, không phải một file application JAR chạy được tại root nếu chưa copy/ghép nội dung.

| Thuộc tính | `tools extract` | `tools extract --layers` |
|---|---|---|
| Đầu ra chính | Một application JAR mỏng + thư mục `lib/` | Các thư mục theo tên layer |
| Mục tiêu | Chạy exploded jar hiệu quả, hỗ trợ CDS/AOT cache tùy JDK/phiên bản | Tách thành Docker/OCI layers dễ cache |
| Lệnh chạy sau extract | `java -jar <dir>/<app>.jar` | Phải ghép các layer vào runtime location đúng trước khi chạy |
| Có nên copy các thư mục `dependencies`, `application`? | Không, layout không như vậy | Có, nếu artifact dùng layer names đó |
| Có thể chỉ đổi `layertools` thành `tools` và giữ Dockerfile cũ? | Không | Chỉ sau khi sửa cú pháp, path, ENTRYPOINT và xác minh artifact |

### 6.4. Tắt tool JAR trong bản mới

Maven plugin **từ Spring Boot 3.3** có cấu hình `includeTools` ở **cấp plugin**, không nằm dưới `layers`:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <includeTools>false</includeTools>
    </configuration>
</plugin>
```

Gradle Groovy DSL:

```groovy
tasks.named("bootJar") {
    includeTools = false
}
```

Nếu bạn tắt `includeTools`, ứng dụng có thể vẫn chạy bình thường qua `java -jar`, nhưng tool mode `-Djarmode=tools` không còn khả dụng trong archive. Đó là lựa chọn phù hợp khi image đã được build bằng cơ chế khác và bạn chủ động muốn giảm thành phần đóng gói, **không** phải cách tắt Spring Boot Loader.

Ngược lại, để tắt **file phân lớp** mà không kết luận về tool JAR:

```xml
<configuration>
    <layers>
        <enabled>false</enabled>
    </layers>
</configuration>
```

Với Boot 3.3+, release notes nêu rõ **tắt layers không còn tự loại tool JAR**; nếu muốn loại implementation, phải dùng `includeTools=false`. Nếu tool vẫn được đóng kèm nhưng thiếu `layers.idx`, không nên mong `list-layers`/`extract --layers` hoạt động bình thường. Hãy kiểm tra file và thử đúng lệnh với chính artifact.

### 6.5. Vì sao Boot 4.1 không dùng layertools?

Spring Boot 4.1 Release Notes xác nhận **loại bỏ chế độ layertools đã deprecated**. Với build từ 4.1, quy trình theo lớp phải chuyển sang:

```bash
java -Djarmode=tools -jar my-app.jar list-layers
java -Djarmode=tools -jar my-app.jar extract --layers --destination extracted
```

Không nên cố sửa bằng việc ép thêm dependency `spring-boot-jarmode-layertools` của 3.2 vào JAR 4.1; các bản loader/mode không phải plugin độc lập có thể hoán đổi tùy ý. Nên nâng cấp công cụ đóng gói và script **theo đúng dòng Spring Boot của ứng dụng**.

## 7. Ví dụ Maven + Spring Boot 3.5.16 có thể build bằng Java 17

Ta tạo **một console app đơn giản**, không cần database hay web server, để tập trung vào hành vi build tool. Ví dụ dùng Spring Boot **3.5.16**, phiên bản được pin để nội dung có thể đối chiếu. Cần JDK 17+, Maven 3.6.3+ phù hợp hoặc Maven Wrapper của dự án và quyền tải dependency từ repository nếu cache chưa có.

### 7.1. Cây thư mục

```text
layer-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/layerlab/LayerLabApplication.java
    └── test/java/com/example/layerlab/LayerLabApplicationTests.java
```

Nếu dự án có Maven Wrapper, còn có `mvnw`, `mvnw.cmd` và `.mvn/wrapper/...`. Đừng giả định wrapper có sẵn khi chỉ tạo POM; có thể dùng Maven đã cài và đặt `mvn` thay `./mvnw`.

### 7.2. pom.xml hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>layer-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <!-- Giữ tools và layer index để thực hành. -->
                    <includeTools>true</includeTools>
                    <layers>
                        <enabled>true</enabled>
                    </layers>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Ở đây:

- `spring-boot-starter-parent` quản lý dependency/plugin versions và cấu hình `repackage` phổ biến.
- `spring-boot-maven-plugin` được khai báo một lần ở app để Maven `package` tạo executable JAR.
- `<includeTools>true</includeTools>` là chính sách **bật đóng kèm tools**; trong Boot 3.5 nó vốn mặc định true, nhưng ghi tường minh để người học thấy cấu hình.
- `<layers><enabled>true</enabled></layers>` giữ `BOOT-INF/layers.idx` cho các commands `list-layers` và `extract --layers`.
- `spring-boot-starter-test` chỉ phục vụ test, không thành runtime dependency trong JAR.

### 7.3. Java main class hoàn chỉnh

`src/main/java/com/example/layerlab/LayerLabApplication.java`:

```java
package com.example.layerlab;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LayerLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayerLabApplication.class, args);
    }

    @Bean
    CommandLineRunner demoRunner() {
        return args -> System.out.println("Layer lab: OK");
    }
}
```

Không khai báo `spring-boot-starter-web` nên chương trình không mở HTTP port; sau startup và khi không có non-daemon tasks khác, nó kết thúc. **Dòng do `CommandLineRunner` in** chính xác:

```text
Layer lab: OK
```

Spring Boot có thể in banner và startup logs bên cạnh; không khẳng định toàn bộ stdout chỉ một dòng.

### 7.4. Test đơn giản theo Java 17/JUnit Jupiter

`src/test/java/com/example/layerlab/LayerLabApplicationTests.java`:

```java
package com.example.layerlab;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class LayerLabApplicationTests {
    @Test
    void javaVersionIsAtLeastSeventeen() {
        assertEquals(true, Runtime.version().feature() >= 17);
    }
}
```

Test này chỉ xác nhận môi trường Java 17+, không khởi tạo Spring context. `mvn clean package` chạy test trước khi đóng gói; nếu JDK của Maven chưa phù hợp, test (hoặc compile) sẽ báo lỗi. Với code thực tế nên kiểm tra behavior của ứng dụng thay vì chỉ kiểm tra phiên bản JVM — bài này dùng test nhẹ để tập trung vào packaging.

### 7.5. Build và chạy

Tại root dự án có `pom.xml`:

```bash
# Nếu project đã có Maven Wrapper:
./mvnw clean package

# Nếu không có Wrapper nhưng Maven đã cài:
mvn clean package

# Chạy executable JAR Boot 3.5:
java -jar target/layer-lab-0.0.1-SNAPSHOT.jar
```

Windows PowerShell có wrapper: `.\mvnw.cmd clean package`. Chỉ sử dụng **một lệnh build**, không bắt buộc chạy cả Maven Wrapper và Maven installed.

### 7.6. Kiểm tra tools dependency và layers.idx

```bash
# JDK jar tool: liệt kê entries:
jar tf target/layer-lab-0.0.1-SNAPSHOT.jar

# Linux/macOS có grep:
jar tf target/layer-lab-0.0.1-SNAPSHOT.jar |
  grep -E '(BOOT-INF/layers.idx|BOOT-INF/lib/spring-boot-jarmode-tools-)'
```

Trên Windows PowerShell:

```powershell
jar tf target/layer-lab-0.0.1-SNAPSHOT.jar |
  Select-String 'BOOT-INF/(layers\.idx|lib/spring-boot-jarmode-tools-)'
```

Trong một build Boot 3.5.16 đúng cấu hình, dự kiến có:

```text
BOOT-INF/layers.idx
BOOT-INF/lib/spring-boot-jarmode-tools-3.5.16.jar
```

Kiểm tra **file JAR thực tế** là quan trọng hơn dự đoán. Việc có `layers.idx` **không chứng minh** tool JAR tồn tại; phải kiểm tra cả hai entry. Khi plugin được cấu hình `includeTools=false`, thiếu tool JAR là đúng mong đợi, không phải lỗi Maven resolution.

### 7.7. Dùng tools liệt kê và trích layer

```bash
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar list-layers

java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar \
  extract --layers --destination extracted
```

Expected layer names (nếu không custom layer configuration):

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

Đây là tên/thuật tự cần nhận diện, không phải cam kết rằng output chứa chính xác bốn dòng, không có log hay định dạng khác. Quan sát nội dung thực của `extracted/`, nhất là layer `application` và `dependencies`.

**Lưu ý đặc biệt về vị trí:** `--destination extracted` là argument của `tools extract`; nó đứng **sau `extract`**, không phải một option của Maven và không phải đường output của `spring-boot-maven-plugin`. Nếu dùng tên destination trùng dữ liệu có sẵn, tool có thể báo lỗi; chọn thư mục sạch.

### 7.8. Thử extract mặc định sang layout khác

Trong một thư mục kiểm tra sạch:

```bash
mkdir -p default-extract-demo
cd default-extract-demo
java -Djarmode=tools -jar ../target/layer-lab-0.0.1-SNAPSHOT.jar extract
cd ..
```

Cấu trúc thường nằm tại:

```text
default-extract-demo/
└── layer-lab-0.0.1-SNAPSHOT/
    ├── layer-lab-0.0.1-SNAPSHOT.jar
    └── lib/...
```

Chạy ứng dụng từ JAR nhỏ:

```bash
java -jar default-extract-demo/layer-lab-0.0.1-SNAPSHOT/layer-lab-0.0.1-SNAPSHOT.jar
```

Dòng in bởi `CommandLineRunner` vẫn là `Layer lab: OK`. Nếu bạn vẫn thấy `dependencies/`, `spring-boot-loader/`,... trong `default-extract-demo` thì cần kiểm tra xem lệnh thực tế có truyền thêm `--layers` hoặc thư mục cũ chưa được dọn không.

## 8. Kiểm tra archive bằng Java 17 thuần, không phụ thuộc Spring

Nếu muốn xác nhận một JAR có **index** và **tool JAR**, có thể dùng Java chuẩn để duyệt ZIP entries. Mã độc lập đặt tại root dưới tên `InspectLayers.java`:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.util.zip.ZipFile;

public final class InspectLayers {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println("Usage: java InspectLayers <jar-file>");
            return;
        }

        try (ZipFile file = new ZipFile(Path.of(args[0]).toFile())) {
            boolean hasLayers = file.getEntry("BOOT-INF/layers.idx") != null;
            boolean hasTools = file.stream().anyMatch(entry ->
                    entry.getName().startsWith(
                            "BOOT-INF/lib/spring-boot-jarmode-tools-"));
            boolean hasLayertools = file.stream().anyMatch(entry ->
                    entry.getName().startsWith(
                            "BOOT-INF/lib/spring-boot-jarmode-layertools-"));

            System.out.println("layers.idx: " + hasLayers);
            System.out.println("tools JAR: " + hasTools);
            System.out.println("layertools JAR: " + hasLayertools);
        }
    }
}
```

Biên dịch/chạy tại root với Java 17+:

```bash
javac InspectLayers.java
java InspectLayers target/layer-lab-0.0.1-SNAPSHOT.jar
```

**Stdout chính xác với artifact Boot 3.5.16 được tạo theo POM ví dụ, khi cả layer index và tools JAR có mặt:**

```text
layers.idx: true
tools JAR: true
layertools JAR: false
```

Đây là kết quả từ việc kiểm tra **ZIP entries** theo tên, không phải phép chứng minh tính tương thích của loader runtime. Một custom build có thể đổi tên/đưa tool dependency theo cách khác; khi đó chương trình chỉ phản ánh quy tắc dò tên của nó. Nó vẫn rất hữu ích để phát hiện JAR thực tế được package với **tool nào** trước khi chạy lệnh `-Djarmode`.

Để kiểm tra một artifact Spring Boot 3.2.12 có layertools:

```bash
java InspectLayers path/to/legacy-app.jar
```

Trong case legacy có file index + layertools dependency và không có tools dependency, kết quả dự kiến:

```text
layers.idx: true
tools JAR: false
layertools JAR: true
```

Không ép kết quả này cho mọi JAR 3.2: plugin có thể cấu hình `includeLayerTools=false` hoặc layers disabled.

## 9. Ví dụ Maven cũ (3.2.12): cần đổi những gì?

Để mô phỏng phiên bản cũ một cách có kiểm soát, **tạo một bản copy độc lập của project ví dụ** và thay trong POM:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.12</version>
    <relativePath/>
</parent>
```

Ở Spring Boot 3.2, **không giữ tham số `includeTools` của POM 3.5**, vì tham số này được thêm từ 3.3. Thay `<configuration>` trong plugin bằng:

```xml
<configuration>
    <layers>
        <enabled>true</enabled>
        <includeLayerTools>true</includeLayerTools>
    </layers>
</configuration>
```

Đây là **các đoạn thay thế trong POM chính**, không phải một POM cũ độc lập để copy nguyên mà không có `<project>`. Những class Java 17 (`LayerLabApplication.java` và unit test) vẫn dùng được với Boot 3.2.12 khi dependency versions tương thích, vì mã chỉ dùng APIs cơ bản.

Build copy dự án:

```bash
mvn clean package

java -Djarmode=layertools -jar target/layer-lab-0.0.1-SNAPSHOT.jar list

mkdir -p legacy-extracted
cd legacy-extracted
java -Djarmode=layertools -jar ../target/layer-lab-0.0.1-SNAPSHOT.jar extract
cd ..
```

Nếu dùng Maven Wrapper trong bản copy, thay `mvn` bằng `./mvnw`. **Không** dùng `java -Djarmode=tools ...` trên Boot 3.2 JAR rồi mong hoạt động; đây không phải mode tích hợp đã được giới thiệu cho nhánh này.

Trong CI thực tế, không nên chạy `mvn clean package` nhiều lần trên cùng checkout rồi so tool behavior mà quên version đã đổi: phải **tách artifact** thành file khác tên/đường dẫn khác hoặc dùng hai checkout/build outputs riêng, để chắc chắn đang thử đúng version.

## 10. Gradle: thay đổi DSL giữa phiên bản cũ và mới

Bản chất JAR mode phụ thuộc **artifact cuối**, không phụ thuộc bạn dùng Maven hay Gradle. Nhưng DSL điều khiển tool JAR thay đổi cùng phiên bản plugin.

### 10.1. Gradle Boot 3.2 Groovy DSL

Trong `build.gradle` của project có `org.springframework.boot` + `java`:

```groovy
tasks.named("bootJar") {
    layered {
        enabled = true
        includeLayerTools = false  // Loại layertools JAR ở bản cũ
    }
}
```

Khi cần dùng layertools để trích xuất, phải **không đặt `includeLayerTools=false`**. Mặc định khi tạo layered archive, Spring Boot plugin thêm layertools JAR; bạn có thể bật lại true rõ ràng nếu muốn.

### 10.2. Gradle Boot 3.5 Groovy DSL

Ví dụ build script **hoàn chỉnh** để dùng cùng `LayerLabApplication.java` ở mục 7:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    includeTools = true
    layered {
        enabled = true
    }
}
```

`settings.gradle` tối thiểu:

```groovy
rootProject.name = 'layer-lab'
```

Với **Gradle Wrapper đã có** và phiên bản Gradle phù hợp Spring Boot 3.5:

```bash
./gradlew clean bootJar

jar tf build/libs/layer-lab-0.0.1-SNAPSHOT.jar

java -Djarmode=tools -jar build/libs/layer-lab-0.0.1-SNAPSHOT.jar list-layers

java -Djarmode=tools -jar build/libs/layer-lab-0.0.1-SNAPSHOT.jar \
  extract --layers --destination extracted
```

Windows PowerShell dùng `.\gradlew.bat` và viết lệnh tools trên một dòng. Maven và Gradle cùng ý tưởng phân lớp, nhưng **không lấy POM `<includeTools>` đem dán vào Groovy**, cũng không dùng `tasks.named('bootJar')` trong Maven.

### 10.3. Kotlin DSL và scope của includeTools

Nếu Gradle project sử dụng `build.gradle.kts`, cú pháp tương ứng là (đoạn cấu hình, không phải file độc lập):

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    includeTools.set(true)
    layered {
        enabled.set(true)
    }
}
```

Khác biệt quan trọng là `includeTools` thuộc **BootJar/BootWar task**, không phải property con của `layered` trong dòng 3.3+. Với một executable WAR, điều chỉnh task `bootWar` và đường dẫn web application layout theo plugin, không giả định mọi WAR có `BOOT-INF/lib` như JAR.

## 11. Dockerfile legacy và mới: đổi lệnh nào, ENTRYPOINT nào?

### 11.1. Dockerfile cho Boot 3.2.x layertools

Ví dụ sau dùng artifact `target/layer-lab-0.0.1-SNAPSHOT.jar` đã build bằng **Boot 3.2**. Đây là Dockerfile nhiều giai đoạn dùng Java 17:

```dockerfile
FROM eclipse-temurin:17-jre AS builder
WORKDIR /builder

COPY target/layer-lab-0.0.1-SNAPSHOT.jar application.jar

RUN mkdir -p extracted
WORKDIR /builder/extracted
RUN java -Djarmode=layertools -jar ../application.jar extract

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=builder /builder/extracted/dependencies/ ./
COPY --from=builder /builder/extracted/spring-boot-loader/ ./
COPY --from=builder /builder/extracted/snapshot-dependencies/ ./
COPY --from=builder /builder/extracted/application/ ./

ENTRYPOINT ["java", "org.springframework.boot.loader.launch.JarLauncher"]
```

Ở đây `layertools extract` đặt file theo bốn layer directories. Các lệnh `COPY` lần lượt **ghép lại layout Boot loader cũ**. Entrypoint class `org.springframework.boot.loader.launch.JarLauncher` đúng với layout loader Spring Boot 3.2. Nếu dùng Boot 2.x cũ hơn, package class launcher có thể khác; phải xác minh manifest/phiên bản trước khi copy đoạn này.

**Không lấy Dockerfile trên để chạy ngay artifact 4.1.** 4.1 đã bỏ layertools; dù trích archive bằng tool khác, entrypoint và loader compatibility cần đánh giá theo JAR mode mới.

### 11.2. Dockerfile cho Boot 3.5+ tools theo lớp

Với **cùng tên artifact** nhưng được build bằng Spring Boot **3.5.16**:

```dockerfile
FROM eclipse-temurin:17-jre AS builder
WORKDIR /builder

COPY target/layer-lab-0.0.1-SNAPSHOT.jar application.jar

RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=builder /builder/extracted/dependencies/ ./
COPY --from=builder /builder/extracted/spring-boot-loader/ ./
COPY --from=builder /builder/extracted/snapshot-dependencies/ ./
COPY --from=builder /builder/extracted/application/ ./

# Lưu ý: sau khi tools extract --layers và COPY, đây là file JAR
# đã được tạo trong layout mới; KHÔNG phải application.jar fat JAR ở builder.
ENTRYPOINT ["java", "-jar", "application.jar"]
```

Lệnh `extract --layers --destination extracted` và `ENTRYPOINT java -jar application.jar` là **mẫu từ tài liệu Spring Boot 3.3+/3.5**. Cách chạy này hỗ trợ layout exploded có application JAR nhỏ và các thư viện ở thư mục thích hợp sau khi copy. Dùng Dockerfile cùng tên artifact và base JRE 17 cho **Boot 3.5**, không áp dụng nguyên nếu dự án Boot 4.x có yêu cầu JDK khác; chọn runtime image phù hợp bản Boot đang dùng.

**Vì sao khác ENTRYPOINT?** Tools 3.3+ xây dựng một layout hướng đến chạy bằng `java -jar` với manifest classpath trỏ tới thư viện đã giải nén. Không nên giữ `ENTRYPOINT ["java","org.springframework.boot.loader.launch.JarLauncher"]` như công thức bắt buộc khi đã chuyển sang tools.

### 11.3. Vì sao phải kiểm tra layer order khi COPY?

Các lệnh `COPY` lần lượt tạo image layers theo thứ tự. Dependency releases được đặt trước, application ở cuối để khi chỉ sửa source ứng dụng, Docker có thể reuse cached layers của thư viện.

Nếu build cấu hình **custom layers**, đường dẫn `extracted/dependencies/` hoặc thứ tự layer có thể khác. Lúc đó:

1. Chạy `list-layers` trên artifact.
2. Trích `layers.idx` hoặc nhìn thư mục output.
3. Điều chỉnh `COPY` cho đúng mọi layer và thứ tự.
4. Kiểm tra app khởi động từ image thật và không thiếu dependency.
5. Đo cache hit/size của image trên CI; không suy performance từ tên layer.

Một Dockerfile không nên hardcode duy nhất một module version khác với artifact mà Maven/Gradle tạo ra. Nên pin đường dẫn artifact cụ thể hoặc copy build output vào một tên nhất quán như `application.jar` trong builder.

## 12. Lỗi thường gặp khi nâng từ layertools lên tools

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Unknown jar mode 'layertools'` trên Boot 4.1 | Mode cũ đã bị loại | Đổi sang `-Djarmode=tools` và lệnh con mới |
| `Unknown jar mode 'tools'` với Boot 3.2 | Artifact cũ không có mode tools | Dùng `layertools` hoặc nâng Boot/plugin rồi build lại |
| `tools list` không được nhận diện | `tools` dùng `list-layers`, không phải `list` | Đổi lệnh con |
| `layertools list-layers` không hoạt động | `layertools` cũ dùng `list` | Đổi về `list` trên artifact legacy |
| Dockerfile dùng `tools extract` nhưng COPY `extracted/dependencies` | Extract mặc định tạo JAR mỏng + `lib`, không chia layer | Dùng `extract --layers --destination extracted` |
| `tools extract --layers` không tìm thấy layer index | `BOOT-INF/layers.idx` vắng/bị disable | Xem archive và bật `layers.enabled` phù hợp |
| JAR có `layers.idx` nhưng jarmode không chạy | Đã đặt `includeTools=false` hoặc legacy `includeLayerTools=false` | Kiểm tra nested tool JAR, cấu hình plugin và build lại |
| Tắt `layers.enabled` nhưng tools JAR vẫn có ở 3.3+ | Layer generation và inclusion tách nhau | Dùng `includeTools=false` nếu thật sự cần loại tool |
| Maven 3.2 báo cấu hình `includeTools` không hợp lệ/không có tác dụng | Cú pháp từ 3.3+ được dùng nhầm | 3.2 dùng `layers.includeLayerTools` |
| Gradle báo `includeLayerTools` không còn phù hợp | Dùng DSL cũ sau upgrade | Chuyển sang `includeTools` ở cấp task |
| Tool không xử lý fully executable archive | JAR có launch script prepended | Tắt launch script khi cần jarmode extract |
| `java -jar ...` khởi động app thay vì in layers | `-Djarmode` đứng sai chỗ (sau `-jar app.jar`) | Đặt `-Djarmode=tools` trước `-jar` |
| Build thành công nhưng tool mode không có | Plain JAR/nhầm `-plain.jar`, tool bị loại | Xem đúng executable archive và `BOOT-INF/lib` |
| Lấy JAR từ root nhưng Dockerfile trỏ `build/libs`/`target` khác | Build tool/đường dẫn output nhầm | Maven thường `target`; Gradle thường `build/libs` |
| Docker ENTRYPOINT không tìm JarLauncher | Giữ entrypoint legacy trong layout tools mới | Dùng `java -jar application.jar` theo Dockerfile 3.3+ |
| Test local chạy nhưng image fail | Copy thiếu layer hoặc base JRE/JDK không tương thích | So `list-layers`, kiểm tra layer dirs, JDK, startup logs |
| Chạy extract nhiều lần bị từ chối ghi | Destination không rỗng | Dùng thư mục mới; xóa an toàn output riêng rồi chạy lại |
| Không thấy layer `snapshot-dependencies` | Dự án không có JAR SNAPSHOT hoặc output trống | Dựa vào index và directory thực, không tự thêm file |
| Tăng số image layers nhưng image không nhanh hơn | Build cache/config hoặc dependencies thay đổi thường xuyên | Đo cache reuse, CPU/IO, kích thước image; tối ưu theo dữ liệu |

### Lỗi cần phân biệt với vấn đề JAR mode

- `UnsupportedClassVersionError`: JRE thấp hơn yêu cầu bytecode của app/Boot; không giải quyết bằng đổi `layertools` ↔ `tools`.
- `ClassNotFoundException`/`NoClassDefFoundError` sau khi chạy image: có thể thiếu runtime JAR hoặc COPY sai layer; kiểm tra classpath/packaging.
- Maven không có goal `build-image` hoặc Gradle không có task `bootJar`: lỗi build plugin/task setup, không phải mode của archive.
- Build cache không hit: còn phụ thuộc thứ tự Dockerfile, nội dung layer, base image và cache policy; file `layers.idx` không tự làm Docker image nhanh.
- CI dùng JAR cũ từ cache dù POM đổi phiên bản: hãy kiểm tra hash/timestamp/artifact path thay vì thử random flags.

## 13. Checklist kiểm thử migration của một dự án thật

### 13.1. Inventory trước upgrade

Tại CI/repository đang dùng, tìm:

```text
-Djarmode=layertools
-Djarmode=tools
layertools extract
layertools list
tools extract
tools list-layers
includeLayerTools
includeTools
BOOT-INF/layers.idx
spring-boot-jarmode-layertools
spring-boot-jarmode-tools
```

Không chỉ sửa Dockerfile: CI scripts, shell scripts, Helm/init containers, build automation và tài liệu triển khai có thể còn gọi mode cũ. Với quyền đọc repository hiện tại, áp dụng tìm kiếm có phạm vi đúng codebase; bài học không yêu cầu sửa các hệ thống đó ngay.

### 13.2. Xác nhận version và artifact thật

1. Đọc **effective POM**/Gradle plugins để biết Spring Boot plugin version.
2. Xác nhận executable JAR đã build tương ứng version, không lấy nhầm plain JAR.
3. Dùng `jar tf` để xem `BOOT-INF/layers.idx`, tool JAR và launcher.
4. Chạy `-Djarmode=tools` hoặc `layertools` đúng **phiên bản**, không chỉ theo tên file.
5. Chạy `list`/`list-layers`; xác nhận mọi layer dùng trong Dockerfile tồn tại.
6. Chạy `extract` vào thư mục sạch; quan sát layout thật trước khi viết `COPY`.
7. Xác nhận startup từ layout trích xuất/Docker image; test chức năng cơ bản.
8. Với 4.1+, bỏ hoàn toàn lời gọi `layertools` trong các script dùng artifact mới.
9. So image cache, size, startup và dependency availability trên CI/runtime đích.
10. Ghi phiên bản tài liệu/release notes dùng để quyết định, tránh copy các ví dụ khác dòng Boot.

### 13.3. Cách chứng minh Dockerfile không vô tình chạy app trong builder

Trong builder stage, goal của JAR mode là **trích xuất**, không phải chạy Spring ApplicationContext. Với ví dụ này, chương trình app in `Layer lab: OK` khi chạy bình thường. Còn lệnh:

```bash
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar list-layers
```

sẽ in thông tin layers, **không kích hoạt `CommandLineRunner`** và không in dòng app `Layer lab: OK` như một side effect của Spring startup. Nếu bạn thấy app startup log ở builder, kiểm tra vị trí `-Djarmode`, tool inclusion và command đã được thực thi.

### 13.4. Chính sách kiểm soát version

- Pin version Spring Boot **plugin và runtime dependencies** tương thích; không tự lấy tool JAR version khác bỏ vào executable archive.
- Maven: nếu dùng `spring-boot-starter-parent`, để parent quản lý plugin version; nếu import BOM riêng, vẫn phải cấu hình Boot plugin/repackage cho app.
- Gradle: nhập Spring Boot BOM hoặc dependency-management plugin phù hợp; áp dụng Boot plugin chỉ tại module tạo executable archive.
- Với Spring Boot 3.2 và 3.5 chạy song song trong một monorepo, **Dockerfile/jarmode invocation phải gắn với artifact cụ thể**, không có một command chung áp cho cả hai nếu chưa phân nhánh.
- Với upgrade lên Boot 4.1, xem luôn **yêu cầu JDK và các thay đổi Spring Framework khác**, ngoài việc đổi tên jar mode.

## 14. Tổng hợp nhanh và bài tập

### Bảng ghi nhớ

| Hỏi | Trả lời |
|---|---|
| `layers.idx` là gì? | Index mô tả cách chia archive thành Docker/OCI layers |
| `classpath.idx` là gì? | Index sắp thứ tự nested JAR trong classpath |
| Spring Boot 3.2 cần mode nào? | `-Djarmode=layertools` |
| Spring Boot 3.5 nên dùng mode nào? | `-Djarmode=tools` |
| Spring Boot 4.1 còn `layertools` không? | **Không**, đã loại bỏ |
| Từ `layertools list` chuyển sang gì? | `tools list-layers` |
| Từ `layertools extract` sang gì khi muốn layer dirs? | `tools extract --layers --destination <dir>` |
| `tools extract` không `--layers` tạo gì? | Layout gồm application JAR nhỏ và thư mục `lib/` |
| Tắt tool JAR Maven 3.2 thế nào? | `layers.includeLayerTools=false` |
| Tắt tool JAR Maven 3.3+ thế nào? | `includeTools=false` |
| Tắt layer index có loại tool JAR trên 3.3+ không? | **Không tự động** |
| Dockerfile mới nên khởi động thế nào? | Với layout tools 3.3+ do ví dụ tạo: `java -jar application.jar` |
| Một archive fully executable có launch script dùng tools extract được? | Không theo hướng dẫn Spring Boot; cần build archive thích hợp |

### Bài tập 1: phân loại ba dòng lệnh

```bash
java -Djarmode=layertools -jar app.jar list
java -Djarmode=tools -jar app.jar list-layers
java -Djarmode=tools -jar app.jar extract
```

**Đáp án:** dòng 1 thuộc giao diện cũ; dòng 2 liệt kê layer theo tools; dòng 3 trích layout mới mặc định, **không** tương đương với cách trích bốn thư mục layer cũ.

### Bài tập 2: kiểm tra Dockerfile sau upgrade

Một Dockerfile cũ dùng:

```dockerfile
RUN java -Djarmode=layertools -jar application.jar extract
COPY --from=builder /builder/dependencies/ ./
ENTRYPOINT ["java", "org.springframework.boot.loader.launch.JarLauncher"]
```

Muốn chuyển sang Boot 3.5/4.1, phải kiểm tra và sửa **cả ba**:

1. Lệnh trích layer đổi thành `java -Djarmode=tools -jar application.jar extract --layers --destination extracted`.
2. Nguồn `COPY` tương ứng `/builder/extracted/dependencies/` (và các layer còn lại), phụ thuộc `WORKDIR` builder.
3. Entrypoint theo layout tools mới là `java -jar application.jar` sau khi ghép các layer; không giữ công thức loader main class cũ mà chưa kiểm tra archive.

### Bài tập 3: giải thích vì sao đổi cấu hình không có hiệu lực

Bạn đã đặt:

```xml
<configuration>
    <layers>
        <enabled>false</enabled>
    </layers>
</configuration>
```

nhưng vẫn thấy `spring-boot-jarmode-tools` trong `BOOT-INF/lib` ở Spring Boot 3.5. Đây **không phải** Maven đã bỏ qua config: từ 3.3, cờ điều khiển tool inclusion được tách thành `<includeTools>false</includeTools>`. Đồng thời hãy xác nhận `layers.idx` thực sự vắng trong archive. Nếu cần cả index lẫn công cụ đều bị loại, cấu hình **cả hai** theo mục đích.

**Kết luận cuối:** `layertools` là cơ chế trích layer cũ; `tools` là cơ chế mới (từ Spring Boot 3.3) với cả đường trích **theo layers** và đường trích **default exploded layout** để chạy ứng dụng hiệu quả. Mốc Spring Boot 4.1 là điểm không thể tiếp tục dựa vào layertools. Quy trình an toàn là **xác nhận version/artifact → xem tool JAR và layers.idx → dùng đúng lệnh → kiểm tra layout → kiểm tra Docker COPY + ENTRYPOINT → chạy lại artifact/image**.

## Tài liệu chính thức để đối chiếu từng phiên bản

- [Spring Boot 2.3 Release Notes — Build layered jars và layertools](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.3-Release-Notes)
- [Spring Boot 3.2.12 Reference — Container Images / layertools](https://docs.spring.io/spring-boot/docs/3.2.12/reference/html/container-images.html)
- [Spring Boot 3.2.12 Maven Plugin — Packaging / includeLayerTools](https://docs.spring.io/spring-boot/docs/3.2.12/maven-plugin/reference/htmlsingle/)
- [Spring Boot 3.3 Release Notes — tools mode, deprecations và includeTools](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes)
- [Spring Boot 3.3 Reference — Efficient Deployments](https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html)
- [Spring Boot 3.5 Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Spring Boot 3.5 — Dockerfiles: tools extract --layers](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 4.1 Release Notes — Removal of layertools mode](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes)
- [Spring Boot 4.1 — Dockerfiles: tools jarmode](https://docs.spring.io/spring-boot/4.1/reference/packaging/container-images/dockerfiles.html)
