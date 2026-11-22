# Tạo archive, đọc archive và sử dụng artifact do task khác sinh trong Gradle

## 1. Mục tiêu học tập

Trong dự án Java, công việc build thường cần đóng gói tài nguyên, mã đã biên dịch, cấu hình hoặc báo cáo thành **archive** (`.zip`, `.tar`, `.tar.gz`, `.jar`), đọc nội dung archive, rồi đưa sản phẩm sang bước phân phối hoặc kiểm thử. Gradle cung cấp các task `Zip`, `Tar`, `Jar`, `Copy`, `Sync` cùng `zipTree`, `tarTree` và Provider API để thực hiện workflow này theo cách **khai báo, lazy và có dependency chính xác**.

Kết thúc bài học, bạn có thể:

1. Chọn đúng task `Zip`, `Tar`, `Jar` cho từng định dạng.
2. Điều khiển tên, nơi lưu và cấu trúc bên trong archive bằng `archiveFileName`, `destinationDirectory`, `from`, `into`, `include`, `exclude`, `rename`.
3. Phân biệt **copy nguyên archive** với **đọc/giải nén entry trong archive**.
4. Dùng `zipTree()` cho ZIP/JAR và `tarTree()` cho TAR/TAR.GZ.
5. Dùng `TaskProvider.flatMap { it.archiveFile }` để task khác tiêu thụ artifact đã sinh, đồng thời giữ thông tin dependency producer.
6. Biết trường hợp cần thêm `dependsOn` khi chuyển đổi archive thành FileTree.
7. Sử dụng `Jar` do Java plugin đăng ký thay vì tự dò đường dẫn `build/libs`.
8. Kiểm tra kết quả bằng Gradle Wrapper, Java/JDK tool hoặc `--dry-run`.
9. Tránh các lỗi duplicate entries, archive rỗng, input không tồn tại, stale artifact, `Sync` xóa dữ liệu, archive độc hại và khác biệt về reproducibility giữa các phiên bản Gradle.

Bài nằm trong nhóm **Tệp và tài nguyên** của Build Tool Gradle. Ví dụ chính dùng Gradle Kotlin DSL (`build.gradle.kts`) và Gradle Wrapper. Phần nào là code độc lập, phần nào chỉ là đoạn bổ sung, đều được ghi rõ.

## 2. Archive, artifact và task graph

Một **archive** là file chứa nhiều entry có tên và đường dẫn bên trong; ví dụ:

~~~text
sample-bundle.zip
└── app/
    ├── README.txt
    └── config/
        └── app.properties
~~~

Một **artifact** là đầu ra do build tạo, có thể là archive nhưng cũng có thể là báo cáo `.txt`, metadata JSON hoặc một file khác. Khi Gradle nói “artifact do task khác sinh”, điều quan trọng không chỉ là file nằm đâu mà còn là **task nào tạo file**.

Một workflow đơn giản:

~~~text
payload/  ------> bundle (Zip)
                     |
                     | archiveFile: Provider<RegularFile>
                     |
              +------+----------------+
              |                       |
              v                       v
        deliverBundle             unpackBundle
         (Copy file ZIP)          (zipTree + Copy)
              |                       |
              v                       v
    delivery/bundle.zip       unpacked/app/*.txt
~~~

Task `deliverBundle` cần chính file ZIP. Task `unpackBundle` cần các entry **bên trong** ZIP. Chúng khác nhau về API nguồn:

~~~kotlin
// Copy nguyên ZIP:
from(bundle.flatMap { it.archiveFile })

// Đọc các entry bên trong ZIP:
from(zipTree(bundle.flatMap { it.archiveFile }))
~~~

Khi một task tiêu thụ sản phẩm của task khác, Gradle phải đưa producer vào task graph trước consumer. Mối liên hệ qua `archiveFile` Provider có thể mang thông tin producer; đường dẫn dạng String thường không.

## 3. Các loại archive và task tương ứng

| Archive | Task | Dùng khi |
| --- | --- | --- |
| `.zip` | `Zip` | Đóng gói file/directory phân phối chung |
| `.tar` | `Tar` | Lưu cấu trúc file theo định dạng TAR |
| `.tar.gz`, `.tgz` | `Tar` với `Compression.GZIP` | TAR được nén gzip |
| `.jar` | `Jar` | Chứa Java `.class`, resources và manifest |
| `.war`/`.ear` | `War`/`Ear` cùng plugin tương ứng | Đóng gói ứng dụng Java ở môi trường hỗ trợ |

**JAR là định dạng dựa trên ZIP**, nên Gradle dùng `zipTree()` để đọc nó. Không cần tìm `jarTree()`.

`Zip`, `Tar` và `Jar` đều làm việc dựa trên **CopySpec**: lấy nguồn qua `from`, lọc, đổi tên, đưa vào đường dẫn đích rồi ghi archive. Khác với `Copy`, archive task ghi **một file kết quả** thay vì trực tiếp copy entry ra thư mục.

### 3.1. Các thuộc tính quan trọng

| Thuộc tính | Kiểu | Tác dụng |
| --- | --- | --- |
| `archiveFileName` | `Property<String>` | Tên file archive, ví dụ `sample-bundle.zip` |
| `destinationDirectory` | `DirectoryProperty` | Thư mục chứa output archive |
| `archiveFile` | `Provider<RegularFile>` | File archive được tính từ tên và thư mục đích; **chỉ đọc** |
| `archiveBaseName` | `Property<String>` | Phần tên cơ bản khi dùng convention đặt tên |
| `archiveAppendix` | `Property<String>` | Nhãn bổ sung giữa tên và version |
| `archiveVersion` | `Property<String>` | Phần version |
| `archiveClassifier` | `Property<String>` | Phần classifier như `docs`, `sources`, `all` |
| `archiveExtension` | `Property<String>` | Phần mở rộng, phụ thuộc định dạng/compression |

Mẫu đặt tên:

~~~text
[baseName][-appendix][-version][-classifier].[extension]
~~~

Ví dụ đặt trực tiếp:

~~~kotlin
tasks.register<Zip>("bundle") {
    archiveFileName.set("sample-bundle.zip")
    destinationDirectory.set(
        layout.buildDirectory.dir("archives")
    )
    from("payload")
}
~~~

Tạo archive ở `build/archives/sample-bundle.zip`.

Không viết `archiveFile.set(...)`: `archiveFile` là Provider kết quả, không phải property để người dùng gán output path. Muốn đổi file kết quả, thay `archiveFileName`, `destinationDirectory` hoặc các phần tên hợp lệ.

## 4. Thực hành hoàn chỉnh: tạo ZIP, phân phối và giải nén

Đây là bài thực hành chính, chạy được mà không cần thư viện ngoài Gradle. Giả sử project có Gradle Wrapper và dùng Gradle 8.x hoặc 9.x.

### 4.1. Chuẩn bị thư mục

~~~text
archive-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── payload/
│   ├── README.txt
│   └── config/
│       └── app.properties
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

**payload/README.txt**

~~~text
Welcome to archive demo
~~~

**payload/config/app.properties**

~~~properties
app.name=archive-demo
~~~

**settings.gradle.kts**

~~~kotlin
rootProject.name = "archive-demo"
~~~

Nếu dự án mới chưa có Wrapper, cần tạo bộ file Wrapper bằng Gradle theo quy trình dự án; những lệnh `./gradlew` chỉ hoạt động khi file thực sự tồn tại.

### 4.2. File build.gradle.kts đầy đủ

~~~kotlin
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.api.tasks.Copy
import org.gradle.api.tasks.bundling.Zip

plugins {
    base
}

// Producer: đóng gói nội dung thư mục payload.
val bundle = tasks.register<Zip>("bundle") {
    archiveFileName.set("sample-bundle.zip")
    destinationDirectory.set(
        layout.buildDirectory.dir("archives")
    )

    from(layout.projectDirectory.dir("payload")) {
        into("app")
    }

    // Cấu hình tường minh để ổn định giữa Gradle 8/9.
    isReproducibleFileOrder = true
    isPreserveFileTimestamps = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}

// Consumer 1: sao chép NGUYÊN FILE ZIP.
// Provider archiveFile giữ thông tin producer.
tasks.register<Copy>("deliverBundle") {
    from(bundle.flatMap { it.archiveFile })
    into(layout.buildDirectory.dir("delivery"))
}

// Consumer 2: giải nén ENTRY TRONG ZIP.
// Dùng dependsOn tường minh khi qua lớp zipTree.
tasks.register<Copy>("unpackBundle") {
    dependsOn(bundle)
    from(zipTree(bundle.flatMap { it.archiveFile }))
    into(layout.buildDirectory.dir("unpacked"))
}
~~~

Các điểm cần hiểu:

- `plugins { base }` cung cấp các convention và task chuẩn như `clean`.
- `tasks.register<Zip>` trả về `TaskProvider<Zip>`; không chạy Zip ở thời điểm đăng ký.
- `from(payload) { into("app") }` đưa **nội dung của payload** dưới prefix `app/` bên trong ZIP; không đóng gói toàn bộ thư mục `payload/` như một entry ngoài cùng.
- File thực tế của Zip được truy cập bằng `bundle.flatMap { it.archiveFile }`.
- `deliverBundle` tiêu thụ Provider output trực tiếp qua `Copy.from(...)`; Gradle có đủ thông tin để suy ra dependency.
- `zipTree(...)` biến ZIP thành `FileTree`; `unpackBundle` thêm `dependsOn(bundle)` nhằm bảo đảm producer chạy trước bước giải nén, kể cả trường hợp lớp chuyển đổi archive không bảo toàn đủ thông tin task dependency.
- Cờ reproducibility được đặt rõ vì Gradle 9 mặc định reproducible archives nhưng Gradle 8 không nhất thiết có cùng mặc định.
- `DuplicatesStrategy.FAIL` phát hiện khi hai file nguồn cùng tạo một entry path bên trong archive.

### 4.3. Chạy trên Linux/macOS hoặc Windows

Linux/macOS:

~~~bash
./gradlew clean deliverBundle unpackBundle
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean deliverBundle unpackBundle
~~~

Cấu trúc kết quả cần quan sát:

~~~text
build/
├── archives/
│   └── sample-bundle.zip
├── delivery/
│   └── sample-bundle.zip
└── unpacked/
    └── app/
        ├── README.txt
        └── config/
            └── app.properties
~~~

**Nội dung chính xác** của `build/unpacked/app/README.txt`:

~~~text
Welcome to archive demo
~~~

**Nội dung chính xác** của `build/unpacked/app/config/app.properties`:

~~~properties
app.name=archive-demo
~~~

Đọc file kết quả bằng terminal:

~~~bash
cat build/unpacked/app/README.txt
cat build/unpacked/app/config/app.properties
~~~

PowerShell:

~~~powershell
Get-Content .\build\unpacked\app\README.txt
Get-Content .\build\unpacked\app\config\app.properties
~~~

Không cố định toàn bộ log Gradle vì số task, thông báo cache, thời gian chạy và định dạng console phụ thuộc phiên bản. **File và nội dung đầu ra** mới là điều bài thực hành muốn chứng minh.

### 4.4. Kiểm tra graph mà chưa chạy action

~~~bash
./gradlew deliverBundle --dry-run --console=plain
~~~

Một phần output điển hình:

~~~text
:bundle SKIPPED
:deliverBundle SKIPPED
~~~

`bundle` xuất hiện **trước** `deliverBundle` dù lệnh không yêu cầu trực tiếp `bundle`. Đây là kết quả inferred dependency qua output Provider.

Tương tự:

~~~bash
./gradlew unpackBundle --dry-run --console=plain
~~~

Dự kiến có:

~~~text
:bundle SKIPPED
:unpackBundle SKIPPED
~~~

Ở workflow giải nén, `dependsOn(bundle)` làm task dependency tường minh. Với `--dry-run`, các task được mô phỏng và không tạo file; `SKIPPED` trong output dry-run không phải lỗi.

### 4.5. Chạy độc lập consumer trên workspace sạch

~~~bash
./gradlew clean deliverBundle
~~~

Task `bundle` phải được xét trước khi `deliverBundle` sao chép ZIP; bạn không cần chạy hai lệnh shell tách biệt.

~~~bash
./gradlew clean unpackBundle
~~~

Task `bundle` cũng được xét trước `unpackBundle`, vì consumer khai báo explicit dependency. Cả hai cách đều để Gradle quản lý thứ tự bằng task graph thay vì tự gọi một task từ action của task khác.

## 5. Vì sao `archiveFile` nên được truyền dưới dạng Provider?

Đây là nguyên tắc quan trọng nhất khi **sử dụng artifact do task khác sinh**.

### 5.1. Cách tốt: output Provider gắn với producer

~~~kotlin
val archiveProducer = tasks.register<Zip>("archiveProducer") {
    archiveFileName.set("product.zip")
    destinationDirectory.set(
        layout.buildDirectory.dir("archives")
    )
    from("payload")
}

tasks.register<Copy>("shipProduct") {
    from(archiveProducer.flatMap { it.archiveFile })
    into(layout.buildDirectory.dir("shipped"))
}
~~~

Ở đây:

1. `archiveProducer` là **TaskProvider**, không phải file.
2. `archiveProducer.flatMap { it.archiveFile }` lấy `Provider<RegularFile>` từ output của task.
3. `Copy.from(...)` nhận Provider chứa file và thông tin task tạo ra file.
4. Khi chỉ chạy `shipProduct`, Gradle có thể tự thêm `archiveProducer` vào graph.
5. Đổi `archiveFileName` hoặc `destinationDirectory` của producer không yêu cầu chỉnh sửa consumer.

Đoạn này là **mẫu task bổ sung**, giả định có file `payload` và plugin/thư viện Gradle API phù hợp; không đăng ký nó cạnh một task cùng tên.

### 5.2. Cách dễ lỗi: hard-code cùng một đường dẫn

~~~kotlin
tasks.register<Copy>("shipBad") {
    from(layout.buildDirectory.file("archives/product.zip"))
    into(layout.buildDirectory.dir("shipped"))
}
~~~

Đây chỉ là **Provider của một vị trí file**, không biết task `archiveProducer` tạo file. Nếu chỉ chạy `shipBad` khi chưa có ZIP, Gradle **không thể tự suy ra dependency** từ path đó. `Copy` có thể không chép gì hoặc task khác trong build có thể báo lỗi validation nếu file được khai báo bắt buộc.

Một chuỗi `"build/archives/product.zip"` không chứa metadata “được tạo bởi task X”.

### 5.3. Không dùng `.get()` quá sớm

~~~kotlin
// Anti-pattern ở configuration phase:
val rawFile = archiveProducer.get().archiveFile.get().asFile

tasks.register<Copy>("shipRawFile") {
    from(rawFile)
    into(layout.buildDirectory.dir("shipped"))
}
~~~

Dùng `.get()` trong lúc cấu hình có thể ép task được realize sớm, làm mất configuration avoidance. `java.io.File` còn không giữ được quan hệ producer như Provider chain. Cách đúng khi muốn tiêu thụ output là:

~~~kotlin
from(archiveProducer.flatMap { it.archiveFile })
~~~

Dòng cuối là **mảnh cấu hình** đặt trong `Copy` hoặc `Zip`; không phải build script hoàn chỉnh nếu đứng riêng.

### 5.4. `from(taskProvider)` cũng là một lựa chọn

`CopySpec.from(...)` hỗ trợ các nguồn như path, File, FileCollection, FileTree, Provider và task/TaskProvider. Khi dùng:

~~~kotlin
tasks.register<Copy>("shipAllTaskOutputs") {
    from(archiveProducer)
    into(layout.buildDirectory.dir("all-outputs"))
}
~~~

Gradle có thể sử dụng các output file được task công bố và giữ task dependency. Nhưng khi producer có **nhiều output** hoặc consumer chỉ cần một archive cụ thể, `from(archiveProducer.flatMap { it.archiveFile })` rõ nghĩa hơn.

**Không trộn lẫn `from(taskProvider)` với việc gọi task action bằng tay.** Gradle tự lập graph và chạy những task cần thiết.

## 6. Sao chép archive khác giải nén archive

Để **chép ZIP nguyên vẹn** sang một thư mục, dùng:

~~~kotlin
from(bundle.flatMap { it.archiveFile })
~~~

Để **đọc entry trong ZIP**, dùng:

~~~kotlin
from(zipTree(bundle.flatMap { it.archiveFile }))
~~~

Ở thao tác thứ hai, vì đã đi qua hàm chuyển ZIP thành FileTree, **thêm `dependsOn(bundle)` là cách an toàn và tường minh** nếu ta cần producer được lập lịch trước khi ZIP được mở.

### 6.1. zipTree trả về FileTree

`zipTree(pathOrProvider)` tạo `FileTree` biểu diễn nội dung bên trong ZIP. FileTree là cấu trúc file có tên và thư mục tương đối, không phải một file `.zip` đơn lẻ. Nó được đánh giá lazy khi có consumer cần nội dung.

Ví dụ cho archive đã có sẵn từ bên ngoài:

~~~kotlin
tasks.register<Copy>("unpackThirdParty") {
    from(zipTree("third-party/assets.zip"))
    into(layout.buildDirectory.dir("third-party-assets"))
}
~~~

**Điều kiện:** file `third-party/assets.zip` phải tồn tại và có định dạng ZIP hợp lệ. Đoạn này là task bổ sung; nếu archive từ bên ngoài bị thiếu, không có task producer nào để tự kéo vào graph.

### 6.2. Không có jarTree

JAR, WAR, EAR dùng ZIP container, nên có thể:

~~~kotlin
tasks.register<Copy>("unpackManifest") {
    from(zipTree("libs/example.jar")) {
        include("META-INF/MANIFEST.MF")
    }
    into(layout.buildDirectory.dir("jar-inspection"))
}
~~~

Đây là ví dụ đọc một file JAR **đã có sẵn** ở `libs/example.jar`. Nó chỉ giải nén manifest nếu entry tồn tại. Không có API riêng `jarTree()` cần dùng ở đây.

### 6.3. Dùng tarTree cho TAR

Tương tự:

~~~kotlin
tasks.register<Copy>("unpackThirdPartyTar") {
    from(tarTree("third-party/assets.tar"))
    into(layout.buildDirectory.dir("third-party-tar"))
}
~~~

Với TAR nén gzip và tên bất thường, có thể chỉ định loại compression:

~~~kotlin
val content = tarTree(resources.gzip("third-party/data.bin"))
~~~

Đây là **mảnh code** tạo FileTree, chỉ đúng nếu `data.bin` thực tế chứa gzip-compressed TAR. `tarTree` có thể tự đoán compression từ phần mở rộng `.tar.gz` hoặc `.tgz` khi được đặt tên phù hợp.

## 7. Lọc và cấu trúc entry bằng CopySpec

Một file archive không nhất thiết phải giữ nguyên cây nguồn. Gradle cung cấp khả năng tổ chức nội dung bằng CopySpec.

### 7.1. Đặt prefix thư mục bằng into

~~~kotlin
tasks.register<Zip>("nestedBundle") {
    archiveFileName.set("nested.zip")
    destinationDirectory.set(
        layout.buildDirectory.dir("archives")
    )
    from("payload") {
        into("distribution")
    }
}
~~~

Nội dung đi vào `distribution/README.txt` và `distribution/config/app.properties`. File source trên filesystem không bị đổi tên hoặc di chuyển.

### 7.2. Chỉ chọn một số file bằng include/exclude

~~~kotlin
tasks.register<Zip>("configOnly") {
    archiveFileName.set("config-only.zip")
    destinationDirectory.set(
        layout.buildDirectory.dir("archives")
    )

    from("payload") {
        include("config/app.properties")
        into("config-data")
    }
}
~~~

Ví dụ chỉ gói file `app.properties`. `include`/`exclude` có thể dùng pattern theo quy tắc Ant/Gradle; không nhầm chúng với thao tác tạo file. Nếu pattern không khớp nguồn, archive có thể trống hoặc không có entry bạn muốn.

### 7.3. Đổi tên entry

~~~kotlin
tasks.register<Zip>("renamedBundle") {
    archiveFileName.set("renamed.zip")
    destinationDirectory.set(
        layout.buildDirectory.dir("archives")
    )

    from("payload") {
        rename("README.txt", "INTRO.txt")
        into("app")
    }
}
~~~

Khi đóng gói, entry `README.txt` đổi thành `app/INTRO.txt`, nhưng **file gốc payload/README.txt vẫn giữ nguyên**.

### 7.4. Khi nhiều nguồn cùng tạo tên entry

Giả sử cả `srcA/config.properties` và `srcB/config.properties` được đưa vào cùng root archive. Hai file cùng tạo `config.properties`, dẫn tới **duplicate entry**.

Có thể đặt:

~~~kotlin
duplicatesStrategy = DuplicatesStrategy.FAIL
~~~

để phát hiện thay vì chấp nhận kết quả mơ hồ. Ngoài `FAIL`, Gradle có các giá trị như `EXCLUDE`, `INCLUDE`, `WARN`, `INHERIT`; chọn theo yêu cầu thật thay vì mặc định che lỗi. Nếu cả hai file đều cần, đặt dưới prefix khác nhau bằng `into("srcA")` và `into("srcB")`.

### 7.5. Phân biệt `into` của archive task và Copy task

Trong `Zip`, `into("app")` ở child CopySpec thay đổi **đường dẫn entry trong archive**. Với `Copy`, `into(layout.buildDirectory.dir("unpacked"))` ở cấp task chỉ **thư mục đích trên ổ đĩa**.

Không dùng `into(layout.buildDirectory.dir("archives"))` ở cấp `Zip` với mục tiêu chọn nơi lưu file ZIP. Đích của Zip được chỉ định bởi `destinationDirectory`.

## 8. Tạo TAR và TAR.GZ

Một TAR chứa nhiều entry theo format TAR; TAR **không mặc nhiên nén**. Muốn có TAR nén gzip, cấu hình thuộc tính `compression`.

Ví dụ trong project có thư mục `payload`:

~~~kotlin
import org.gradle.api.tasks.bundling.Compression
import org.gradle.api.tasks.bundling.Tar

tasks.register<Tar>("bundleTarGz") {
    compression = Compression.GZIP
    archiveFileName.set("sample-bundle.tar.gz")
    destinationDirectory.set(
        layout.buildDirectory.dir("archives")
    )

    from("payload") {
        into("app")
    }

    isReproducibleFileOrder = true
    isPreserveFileTimestamps = false
}
~~~

Đây là **mảnh bổ sung** vào build.gradle.kts của project ở mục 4. Đặt hai dòng `import` ở đầu file, cùng các import đã có. Lệnh:

~~~bash
./gradlew bundleTarGz
~~~

Kết quả:

~~~text
build/archives/sample-bundle.tar.gz
~~~

**Chỉ đổi tên file thành `.tar.gz` không tự thực hiện gzip compression.** Bảo đảm `compression = Compression.GZIP` thực sự được khai báo.

### 8.1. Giải nén TAR được task khác tạo

Nếu cần dùng lại task Tar, lưu TaskProvider:

~~~kotlin
val tarProducer = tasks.register<Tar>("tarProducer") {
    compression = Compression.GZIP
    archiveFileName.set("package.tar.gz")
    destinationDirectory.set(layout.buildDirectory.dir("archives"))
    from("payload")
}

tasks.register<Copy>("unpackTarProducer") {
    dependsOn(tarProducer)
    from(tarTree(tarProducer.flatMap { it.archiveFile }))
    into(layout.buildDirectory.dir("tar-unpacked"))
}
~~~

Đây là cặp task **riêng**, không trùng tên với `bundleTarGz`. Nó cần import `Tar`, `Compression`, `Copy`. `dependsOn(tarProducer)` bảo đảm TAR.GZ được tạo trước khi giải nén.

### 8.2. Đừng dùng nhầm zipTree và tarTree

- `.zip` và `.jar`: dùng `zipTree`.
- `.tar`: dùng `tarTree`.
- `.tar.gz`, `.tgz`: dùng `tarTree`, Gradle nhận diện compression từ tên phù hợp hoặc `resources.gzip`.
- Không đọc `.tar.gz` bằng `zipTree` dù cả hai đều “là file nén”.

Nếu một bên thứ ba đặt sai đuôi file, hãy kiểm tra format thực tế thay vì suy luận hoàn toàn từ tên.

## 9. Tạo JAR bằng Java plugin và dùng artifact đó ở task khác

Với dự án Java, plugin `java` tự đăng ký task `jar`. Nó biết các output class/resource của quá trình biên dịch; thường nên cấu hình **task sẵn có** thay vì tự Zip các `.class` từ path cứng.

### 9.1. Dự án Java nhỏ chạy được

Tạo thư mục riêng:

~~~text
jar-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── src/main/java/example/Main.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/...
~~~

**settings.gradle.kts**

~~~kotlin
rootProject.name = "jar-demo"
~~~

**src/main/java/example/Main.java**

~~~java
package example;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Hello from JAR");
    }
}
~~~

**build.gradle.kts**

~~~kotlin
import org.gradle.api.tasks.Copy
import org.gradle.jvm.tasks.Jar

plugins {
    java
}

// Task jar của Java plugin đã có trong project.
val applicationJar = tasks.named<Jar>("jar") {
    archiveFileName.set("hello.jar")
    manifest {
        attributes("Main-Class" to "example.Main")
    }
}

// Consumer: chép file JAR mà không hard-code build/libs.
tasks.register<Copy>("stageJar") {
    from(applicationJar.flatMap { it.archiveFile })
    into(layout.buildDirectory.dir("staged"))
}
~~~

Nếu JDK và Wrapper hợp lệ, chạy:

~~~bash
./gradlew stageJar
java -jar build/libs/hello.jar
~~~

Trong PowerShell:

~~~powershell
.\gradlew.bat stageJar
java -jar .\build\libs\hello.jar
~~~

Stdout của **chương trình Java**:

~~~text
Hello from JAR
~~~

Gradle tạo:

~~~text
build/libs/hello.jar
build/staged/hello.jar
~~~

`stageJar` tự kéo theo `jar` và những task compile/resources cần thiết do `jar` phụ thuộc; không cần chạy riêng hai lệnh Gradle.

Vì ứng dụng Java này chỉ dùng standard library, việc chạy `java -jar` không cần runtime dependency bên ngoài. Với ứng dụng thực tế, **JAR thường không chứa toàn bộ thư viện dependency**; cần chuẩn bị classpath/distribution phù hợp hoặc dùng plugin dành cho executable/fat JAR.

### 9.2. Lấy một entry trong JAR

Bổ sung vào build.gradle.kts của `jar-demo`:

~~~kotlin
tasks.register<Copy>("extractJavaClass") {
    dependsOn(applicationJar)
    from(zipTree(applicationJar.flatMap { it.archiveFile })) {
        include("example/Main.class")
    }
    into(layout.buildDirectory.dir("extracted-classes"))
}
~~~

Lệnh:

~~~bash
./gradlew extractJavaClass
~~~

File `build/extracted-classes/example/Main.class` là bytecode đã được trích từ JAR. Vì JAR là ZIP, `zipTree` đọc được entry này. Task khai báo `dependsOn` để JAR được build trước khi mở archive.

### 9.3. Gói JAR vào ZIP distribution

~~~kotlin
import org.gradle.api.tasks.bundling.Zip

tasks.register<Zip>("packageApplication") {
    archiveFileName.set("application.zip")
    destinationDirectory.set(
        layout.buildDirectory.dir("distributions")
    )
    from(applicationJar.flatMap { it.archiveFile }) {
        into("lib")
    }
}
~~~

Đoạn trên bổ sung vào dự án jar-demo và cần import Zip ở đầu file. ZIP chứa entry `lib/hello.jar`. Vì `from(...)` nhận Provider output của `jar`, Gradle có thể suy ra dependency. Không cần dùng `zipTree` ở đây vì mục tiêu là **giữ nguyên file JAR bên trong ZIP**.

**Lưu ý:** ghép nhiều JAR bằng cách giải nén rồi đưa vào một JAR khác có thể gây trùng entry, hỏng manifest hoặc thiếu service metadata. Đó là bài toán *uber/fat JAR*; nên dùng công cụ/plugin chuyên dụng như Shadow khi nhu cầu đòi hỏi.

## 10. Đọc ZIP bằng Java 17 (bổ sung cho zipTree)

Trong Gradle build logic, `zipTree` là cách đọc archive phổ biến. Nếu cần một chương trình Java độc lập kiểm tra ZIP, JDK có `java.util.zip.ZipFile`.

Dùng chính ZIP của project `archive-demo` mục 4. Tạo file **InspectZip.java** ở root:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public final class InspectZip {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Require one ZIP path");
        }

        try (ZipFile zip = new ZipFile(args[0])) {
            Collections.list(zip.entries()).stream()
                .filter(entry -> !entry.isDirectory())
                .map(ZipEntry::getName)
                .sorted()
                .forEach(name -> System.out.println("ENTRY " + name));

            ZipEntry readme = zip.getEntry("app/README.txt");
            if (readme == null) {
                throw new IllegalStateException("README not found");
            }

            try (var input = zip.getInputStream(readme)) {
                String text = new String(
                    input.readAllBytes(), StandardCharsets.UTF_8
                ).trim();
                System.out.println("README=" + text);
            }
        }
    }
}
~~~

Chạy trên Linux/macOS:

~~~bash
./gradlew bundle
javac InspectZip.java
java InspectZip build/archives/sample-bundle.zip
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat bundle
javac InspectZip.java
java InspectZip .\build\archives\sample-bundle.zip
~~~

Stdout chính xác với hai file nguồn của ví dụ:

~~~text
ENTRY app/README.txt
ENTRY app/config/app.properties
README=Welcome to archive demo
~~~

Ở đây `.sorted()` đảm bảo thứ tự hai dòng `ENTRY` không phụ thuộc thứ tự lưu entry trong ZIP. `try (ZipFile ...)` đảm bảo đóng file, còn `readAllBytes()` chỉ phù hợp khi file đầu vào nhỏ và đáng tin. Khi đọc archive ngoài Internet, cần kiểm soát dung lượng trước khi dùng cách đọc toàn bộ vào RAM.

Đoạn Java này **không thực hiện giải nén** ra filesystem; nó liệt kê entry và đọc trực tiếp một entry. Mục đích là phân biệt “đọc archive” với “copy archive ra thư mục”.

## 11. Khi nào cần dependsOn và khi nào dependency được suy ra?

| Quan hệ | Ví dụ | Có thêm producer vào task graph? |
| --- | --- | --- |
| Output Provider → input của Copy | `from(bundle.flatMap { it.archiveFile })` | Có, khi Provider mang task producer metadata |
| Explicit dependency | `dependsOn(bundle)` | Có |
| Ordering mạnh | `mustRunAfter(bundle)` | Không |
| Ordering mềm | `shouldRunAfter(bundle)` | Không bảo đảm thứ tự và không thêm producer |
| `zipTree` tạo FileTree | `from(zipTree(...))` | Không nên mặc định nó luôn giữ trọn producer metadata; thêm explicit dependency khi producer bắt buộc |

### 11.1. Nếu chỉ có một file path

Một `String` như `"build/archives/sample-bundle.zip"` chỉ biểu diễn vị trí. Gradle không biết file này do `bundle` tạo. Đưa trực tiếp path vào `from` không tự kéo `bundle` vào graph. Đây là lỗi thường gặp khi build tình cờ thành công trên máy đã có artifact cũ nhưng thất bại ở CI sạch.

### 11.2. Vì sao không dùng mustRunAfter?

~~~kotlin
tasks.named("unpackBundle") {
    mustRunAfter("bundle")
}
~~~

Đoạn này **chỉ** yêu cầu thứ tự khi cả hai task đều đã được chọn. Nếu chỉ chạy `unpackBundle`, `mustRunAfter` không tự bổ sung `bundle`. Consumer cần output producer phải khai báo dependency dữ liệu hoặc explicit `dependsOn`.

### 11.3. Cẩn trọng với Provider độc lập

Một Provider được tạo qua `providers.provider { ... }` có thể tính giá trị lazy nhưng không tự có task producer metadata. Không bọc `bundle.get().archiveFile.get().asFile` trong Provider tùy ý chỉ để trì hoãn tính path; nó có thể làm mất inferred dependency. Lấy Provider trực tiếp từ TaskProvider bằng `flatMap`.

### 11.4. Khi producer có nhiều output

`from(taskProvider)` có thể dùng tập output được task công bố. Tuy nhiên nếu consumer chỉ cần **một file archive**, dùng `from(taskProvider.flatMap { it.archiveFile })` rõ ràng và tránh vô tình copy các output khác.

## 12. Archive reproducibility và version Gradle

Hai file ZIP có cùng nội dung nhưng hash khác nhau nếu:

- Thứ tự các entry khác nhau.
- Timestamp của từng entry khác nhau.
- Quyền file/thư mục khác nhau.
- Input thực sự khác byte (encoding, thời gian sinh mã, JDK biên dịch, dữ liệu không xác định).

Gradle 9.0 trở lên mặc định tạo archive theo hướng **reproducible** đối với các `AbstractArchiveTask` (`Zip`, `Tar`, `Jar`, v.v.): thứ tự entry được chuẩn hóa, timestamps cố định và quyền file/thư mục mặc định ổn định. Với Gradle 8.x và cũ hơn, không nên giả định cùng mặc định.

Khi cần hành vi rõ ràng trên những phiên bản hỗ trợ, cấu hình:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isReproducibleFileOrder = true
    isPreserveFileTimestamps = false
}
~~~

Đưa import lên đầu `build.gradle.kts`. Hai thuộc tính này giúp ổn định metadata archive, nhưng **không làm input tự động deterministic**. Nếu bạn nhúng timestamp hiện tại vào README trong build, hai archive vẫn có thể khác nhau.

### 12.1. Permission của file và script

Gradle 9 dùng quyền mặc định ổn định cho file (`0644`) và thư mục (`0755`) trong archive. Nếu gói shell script cần bit executable, phải cấu hình quyền phù hợp cho entry đó. Không mặc định bật lại toàn bộ quyền filesystem nếu mục tiêu là byte-for-byte reproducibility, vì permission đầu vào có thể khác giữa máy.

### 12.2. Hash artifact

Muốn so sánh hai bản archive có giống byte hay không, có thể dùng công cụ SHA-256 của hệ điều hành hoặc JDK. Nhưng khác hash không chỉ do Gradle: khác JDK patch release, build code hay tài nguyên cũng có thể làm file khác. Khi điều tra, kiểm tra cả **input fingerprint, cấu hình archive và toolchain**.

## 13. Copy so với Sync khi giải nén

`Copy` chỉ sao chép/cập nhật file theo nguồn, thường **không xóa file đích cũ** không còn xuất hiện trong archive. `Sync` có thể xóa nội dung trong thư mục đích để đồng bộ với nguồn.

Mẫu đồng bộ nếu thư mục đích **chỉ do task này sở hữu**:

~~~kotlin
import org.gradle.api.tasks.Sync

tasks.register<Sync>("syncUnpackedBundle") {
    dependsOn(bundle)
    from(zipTree(bundle.flatMap { it.archiveFile }))
    into(layout.buildDirectory.dir("synced-bundle"))
}
~~~

Đây là mảnh task bổ sung cho project archive-demo ở mục 4, cần đặt import ở đầu file. Chỉ dùng `Sync` trong thư mục build riêng. Nếu bạn đặt `into(".")` hoặc một thư mục dùng chung, các file không có trong nguồn có thể bị xóa — **không làm vậy**.

### 13.1. UP-TO-DATE, FROM-CACHE và SKIPPED

Gradle có thể không chạy action dù một task vẫn xuất hiện trong graph:

- `UP-TO-DATE`: input/output không đổi theo kiểm tra của Gradle.
- `FROM-CACHE`: khôi phục output từ build cache nếu task/cấu hình hỗ trợ.
- `NO-SOURCE`: task không có nguồn hợp lệ để xử lý trong trường hợp được hỗ trợ.
- `SKIPPED`: bị bỏ qua do điều kiện hoặc mô phỏng `--dry-run`.

Vì vậy một consumer “không thấy log của producer” không chứng minh producer đã biến mất khỏi graph. Hãy nhìn trạng thái task và file output.

### 13.2. File nguồn không tồn tại

`Copy.from("wrong-path")` có thể không chép dữ liệu nào nếu file không tồn tại; việc task không báo lỗi ngay không chứng minh archive hợp lệ. Với artifact quan trọng, nên kiểm tra nguồn và xác minh entry thiết yếu sau khi tạo archive, thay vì chỉ dựa vào trạng thái BUILD SUCCESSFUL.

## 14. Tính an toàn khi xử lý archive

Archive do người khác cung cấp không chỉ mang nội dung; nó có thể chứa entry path bất thường, symbolic link, file rất lớn hoặc số lượng file cực lớn.

**Những rủi ro cần cân nhắc:**

1. **Path traversal/Zip Slip:** tên entry cố tình thoát thư mục đích. Không cho rằng mọi công cụ giải nén tự kiểm soát hết mọi trường hợp; cần xác minh nguồn archive và xử lý path hợp lệ.
2. **Zip bomb:** archive nén rất nhỏ nhưng giải ra quá nhiều dữ liệu, tiêu tốn RAM, CPU hoặc disk.
3. **Ghi đè file:** entry trùng đường dẫn làm mất dữ liệu cũ hoặc gây kết quả khó đoán.
4. **Symlink/permissions:** entry có link hoặc quyền nhạy cảm có thể ảnh hưởng môi trường, đặc biệt với các công cụ giải nén khác nhau.
5. **Sync sai đích:** một task đồng bộ xóa file của người dùng trong thư mục dùng chung.

Để giảm rủi ro: dùng nguồn artifact tin cậy; giải nén vào thư mục riêng trong `build/` (không phải root project hoặc home directory); kiểm tra tên entry, kích thước và số lượng file khi xử lý nguồn không đáng tin; dùng duplicate policy rõ ràng; không bật thực thi nội dung vừa giải nén nếu chưa được kiểm chứng.

Gradle `zipTree`/`tarTree` giúp thao tác file thuận tiện, **không phải bộ quét bảo mật**. Tác vụ bảo mật chuyên sâu có thể yêu cầu công cụ kiểm tra format/archive riêng.

## 15. Sử dụng artifact trong multi-project và publishing

Trong project nhiều module, artifact được chia sẻ qua hai kiểu quan hệ:

- **Nội bộ build:** task của module khác dùng output Provider/TaskProvider khi API và phạm vi cấu hình cho phép.
- **Artifact theo dependency/variant:** module consumer khai báo project dependency; Gradle resolve một variant/artifact do producer cung cấp.

Ví dụ khi `:core` có Java Library plugin và `:app` dùng Java:

~~~kotlin
dependencies {
    implementation(project(":core"))
}
~~~

Đây là mảnh code cho `:app/build.gradle.kts` có plugin cung cấp configuration `implementation`. Gradle có thể lựa chọn artifact/classes phù hợp và tạo task dependency theo variant. Không cần tự hard-code `../core/build/libs/core.jar`.

Với artifact ZIP tùy chỉnh giữa các module, cần cân nhắc **consumable configurations/outgoing variants** nếu đây là giao diện công khai cho nhiều project. Chỉ có một task `Zip` chưa đồng nghĩa archive đó được publish hay tự động là dependency tiêu thụ được.

**Phân biệt ba tầng:**

~~~text
Task output         : archiveFile Provider
Dependency/variant  : thông tin tiêu thụ giữa project
Publication         : công bố artifact lên repository
~~~

Tạo `Zip` không tự tải artifact lên Maven repository. Nếu chỉ muốn chuyển ZIP cho một task khác trong cùng project, Provider output là đủ; không cần dựng một publication.

## 16. Những lỗi thường gặp và cách sửa

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Consumer chỉ chép một file ZIP, không giải nén | Dùng `from(archiveFileProvider)` | Dùng `from(zipTree(...))` |
| Consumer giải nén thành nhiều file dù chỉ muốn ZIP | Dùng `zipTree` khi cần archive nguyên vẹn | Dùng `from(producer.flatMap { it.archiveFile })` |
| CI sạch chạy consumer không thấy producer | Dùng raw path không có dependency | Giữ output Provider hoặc `dependsOn` |
| File ZIP cũ tiếp tục được gửi | Consumer hard-code name/path | Dùng `archiveFile` của producer |
| `zipTree` mở file chưa tồn tại | Producer chưa được chọn hoặc path sai | Thêm `dependsOn` và kiểm tra output |
| Archive chứa entry ở path sai | Child `into` sai hoặc thêm prefix không mong muốn | Kiểm tra `from`/`into` và liệt kê entry |
| Archive rỗng | Nguồn sai hoặc include/exclude lọc hết | Kiểm tra source và task graph |
| Duplicate entry báo lỗi | Nhiều nguồn tạo cùng relative path | Tách prefix hoặc quyết định duplicatesStrategy |
| `.tar.gz` không phải gzip | Đổi tên file nhưng quên `Compression.GZIP` | Đặt compression thực |
| Task có trong graph nhưng không chạy action | UP-TO-DATE, FROM-CACHE, SKIPPED | Xem trạng thái/log và output |
| Hash ZIP khác trên CI | File order/timestamps/permissions/toolchain khác | Reproducible settings và deterministic inputs |
| `java -jar` báo thiếu Main-Class | Chưa cấu hình manifest | Đặt `Main-Class` trong task jar |
| `java -jar` báo thiếu class runtime | JAR chưa gồm thư viện phụ thuộc | Dùng distribution/runtime classpath phù hợp |
| `Sync` xóa file ngoài archive | Sync làm đúng chức năng đồng bộ | Chỉ dùng thư mục output riêng |
| Đọc JAR bằng tarTree thất bại | Sai định dạng | JAR dùng zipTree |
| Custom archive bị hiểu là đã publish | Chưa có publication/variant | Cấu hình publishing/outgoing artifact riêng |

## 17. Kiểm tra và debug với Gradle Wrapper

Lệnh phổ biến:

~~~bash
./gradlew bundle --dry-run --console=plain
./gradlew deliverBundle --dry-run --console=plain
./gradlew unpackBundle --info --console=plain
./gradlew tasks --all --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat bundle --dry-run --console=plain
.\gradlew.bat deliverBundle --dry-run --console=plain
.\gradlew.bat unpackBundle --info --console=plain
~~~

`--dry-run` chỉ mô phỏng task actions; nếu build logic có tác dụng phụ ngay trong configuration, dry-run không chặn được mọi tác động ấy. `--info` giúp hiểu vì sao task được thực thi, bị skip hoặc up-to-date, nhưng có thể in log dài.

Nếu có JDK tool:

~~~bash
jar tf build/archives/sample-bundle.zip
~~~

JDK `jar` có thể liệt kê ZIP/JAR; output phụ thuộc thứ tự entry và việc archive có chứa directory entries. Không dùng nguyên văn output liệt kê như điều kiện duy nhất; hãy xác minh những entry cần có.

### 17.1. Checklist chẩn đoán

1. File source có thực sự tồn tại ở `from(...)` không?
2. Task tạo artifact đã đặt `archiveFileName` và `destinationDirectory` đúng chưa?
3. Đường dẫn entry trong ZIP có đúng `into`/include/exclude không?
4. Consumer cần nguyên archive hay nội dung bên trong?
5. Consumer có dùng output Provider, hay chỉ dùng path `String`/`File`?
6. Nếu có `zipTree`/`tarTree` cho archive sinh động, đã bảo đảm task producer ở graph chưa?
7. Có vấn đề duplicate entries không?
8. Có phải output đã UP-TO-DATE chứ không phải task không chạy?
9. Nếu archive hash khác, timestamps/order/permissions hoặc file input nào đổi?
10. Nếu dùng `Sync`, thư mục đích có thật sự thuộc sở hữu task không?

## 18. Bài tập thực hành và đáp án

**Câu 1:** Task `bundle` tạo ZIP, task `release` cần chép nguyên ZIP. Viết `from(...)` thế nào?

**Đáp án:**

~~~kotlin
tasks.register<Copy>("release") {
    from(bundle.flatMap { it.archiveFile })
    into(layout.buildDirectory.dir("release"))
}
~~~

Đoạn này giả định có TaskProvider<Zip> tên `bundle` từ mục 4.

**Câu 2:** Muốn giải nén nội dung ZIP sinh bởi `bundle` vào `build/extract`?

**Đáp án:**

~~~kotlin
tasks.register<Copy>("extract") {
    dependsOn(bundle)
    from(zipTree(bundle.flatMap { it.archiveFile }))
    into(layout.buildDirectory.dir("extract"))
}
~~~

**Câu 3:** Vì sao `mustRunAfter(bundle)` không đủ?

**Đáp án:** Vì `mustRunAfter` chỉ sắp thứ tự khi cả hai task có trong graph; nó không tự chọn producer khi chỉ yêu cầu consumer. Dùng inferred dependency hoặc `dependsOn`.

**Câu 4:** Task `jar` do Java plugin tạo, làm sao lấy file output bất kể version hay classifier thay đổi?

**Đáp án:** Dùng `tasks.named<Jar>("jar").flatMap { it.archiveFile }`, thay vì viết cứng `build/libs/...`.

**Câu 5:** Khi đọc JAR, dùng `zipTree` hay `tarTree`?

**Đáp án:** `zipTree`, vì JAR là archive ZIP.

**Câu 6:** Có một task `Tar` đặt `archiveFileName` thành `data.tar.gz` nhưng không có `Compression.GZIP`. Nó chắc chắn là gzip TAR chưa?

**Đáp án:** Chưa. Cần cấu hình compression thật, không chỉ đặt phần mở rộng.

**Câu 7:** Archive đầu ra cùng nội dung nhưng hash khác giữa hai máy. Kiểm tra gì?

**Đáp án:** Thứ tự entry, timestamps, permissions, byte input, JDK/toolchain; đặt reproducibility đúng phiên bản Gradle.

**Câu 8:** Dùng `Sync` giải nén vào thư mục dữ liệu chung có an toàn không?

**Đáp án:** Không. Sync có thể xóa file không thuộc nguồn; chỉ dùng thư mục output riêng, hoặc dùng Copy nếu cần giữ file đích.

## 19. Tổng kết ngắn gọn

**Nhớ bốn mẫu công việc:**

~~~text
TẠO ZIP / TAR / JAR
    task + from(source) + archiveFileName + destinationDirectory

CHÉP NGUYÊN ARCHIVE
    Copy.from(producer.flatMap { it.archiveFile })

ĐỌC / GIẢI NÉN
    Copy.from(zipTree(...)) hoặc Copy.from(tarTree(...))
    + đảm bảo producer dependency khi archive được task khác tạo

GIỮ BUILD ĐÚNG VÀ TÁI LẬP
    TaskProvider + Provider + đúng format + duplicate strategy
    + reproducible archive settings + kiểm tra entry đầu ra
~~~

**Quy tắc quyết định:** Nếu task B cần sản phẩm của task A, hãy lấy sản phẩm **qua output Provider của A**. Nếu muốn copy file archive, truyền Provider trực tiếp; nếu muốn đọc các entry, chuyển nó thành FileTree, đồng thời bảo đảm task A có trong graph. Cách làm này giảm phụ thuộc path cứng, giúp Gradle lên thứ tự chính xác và cập nhật artifact khi producer thay đổi.

## 20. Tài liệu chính thức

- Gradle — Working With Files: https://docs.gradle.org/current/userguide/working_with_files.html
- Gradle — Implementing Custom Tasks: https://docs.gradle.org/current/userguide/implementing_custom_tasks.html
- Gradle — Controlling Task Execution: https://docs.gradle.org/current/userguide/controlling_task_execution.html
- Gradle — Configuring Tasks Lazily: https://docs.gradle.org/current/userguide/lazy_configuration.html
- Gradle — Best Practices for Tasks: https://docs.gradle.org/current/userguide/best_practices_tasks.html
- Gradle — Task Validation Problems: https://docs.gradle.org/current/userguide/validation_problems.html
- Gradle — Zip Kotlin DSL API: https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.tasks.bundling/-zip/index.html
- Gradle — Tar Kotlin DSL API: https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.tasks.bundling/-tar/index.html

Đường dẫn `current` mô tả bản Gradle hiện hành. Khi sử dụng trong repository cụ thể, hãy xem **phiên bản Gradle Wrapper thực tế**, đặc biệt khi dự án còn dùng Gradle 8 hoặc phiên bản cũ hơn với mặc định reproducibility khác Gradle 9.