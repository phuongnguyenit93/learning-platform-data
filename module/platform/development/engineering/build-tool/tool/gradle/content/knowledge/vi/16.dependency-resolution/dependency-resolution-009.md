# Cache metadata, changing module, offline và refresh-dependencies trong Gradle

## 1. Mục tiêu: hiểu chính xác Gradle đang “cache” điều gì

Một lệnh Gradle như `./gradlew build` có thể chạy nhanh ở lần thứ hai vì không phải tải lại dependency. Nhưng sự khác biệt giữa hai lần build không chỉ đến từ file JAR đã có trên đĩa. Gradle còn lưu **metadata của quá trình phân giải dependency**: phiên bản được chọn cho một phiên bản động, thông tin module và dependency bắc cầu, thông tin artifact, thậm chí cả kết quả “module không tồn tại ở repository này”.

Khi dependency thay đổi ở máy chủ mà Gradle vẫn sử dụng bản cũ, bốn khái niệm trong tiêu đề rất dễ bị lẫn:

1. **Metadata cache**: dữ liệu đã ghi nhớ về kết quả tra cứu và phân giải module/artifact, gắn với repository và thời điểm tra cứu.
2. **Changing module**: module có thể được **xuất bản lại với cùng một version**, ví dụ Maven `1.0-SNAPSHOT` hoặc một dependency được đánh dấu `changing = true`.
3. **Offline mode**: cờ `--offline` bảo Gradle **không truy cập mạng để phân giải dependency**, thay vào đó dùng dữ liệu dependency đã lưu trong cache.
4. **Refresh dependencies**: cờ `--refresh-dependencies` yêu cầu Gradle **kiểm tra lại dữ liệu phân giải và artifact ở repository** thay vì tin thời hạn cache thông thường; nó **không xóa cache và không bắt buộc tải lại mọi JAR**.

Bài học thuộc mục **Phân giải dependency** của Build Tool Gradle. Các ví dụ dùng **Groovy DSL** (`settings.gradle`, `build.gradle`), Gradle Wrapper và Java 17. Phần thực hành chính dùng thư viện có version cố định để có chương trình Java chạy được; các thí nghiệm dynamic/changing là những biến thể riêng, cần đúng repository và quyền publish nếu muốn quan sát một module thực sự thay đổi.

Kết quả sau bài: bạn có thể phân biệt cache metadata với artifact cache và các cache khác; chọn `--offline` hay `--refresh-dependencies` đúng tình huống; điều chỉnh hai TTL khác nhau; chẩn đoán vì sao một phiên bản/JAR “cũ” vẫn xuất hiện; và thiết kế CI tránh quá tải repository hoặc khiến build không tái lập.

## 2. Khi Gradle resolve dependency: những bước nào có thể được cache?

Giả sử mã build khai báo:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

Khi một task cần `compileClasspath` hoặc `runtimeClasspath`, Gradle thực hiện các công việc đại ý:

~~~text
build.gradle: group:name:version được yêu cầu
                   |
                   v
         Xác định configuration và attributes
                   |
                   v
      Tra cứu metadata của các repository
            |                |
          có cache        cần kiểm tra mạng
            |                |
            +--------+-------+
                     |
                     v
       Chọn component, version và variant
                     |
                     v
       Tìm artifact metadata và JAR
            |                |
         JAR đã có       JAR chưa có/đã đổi
            |                |
            +--------+-------+
                     |
                     v
        Đưa file vào task classpath
                     |
                     v
          compileJava / test / run / ...
~~~

Gradle có thể tái dùng file tải về mà vẫn **liên hệ repository để xác thực metadata hoặc checksum**, hoặc có đủ metadata nhưng chưa có artifact thực sự cần cho task. Vì thế nhìn thấy `commons-lang3-3.17.0.jar` trên đĩa **không chứng minh mọi graph, configuration và repository đã sẵn sàng chạy offline**.

### 2.1. Hai lớp chính của dependency cache

Trong `$GRADLE_USER_HOME/caches`, dependency cache của Gradle thường có hai thành phần:

| Lớp | Dữ liệu | Vì sao cần |
| --- | --- | --- |
| **File store** | File nhị phân/JAR và các file metadata thô như POM, Ivy, Gradle Module Metadata được tải về | Tránh tải lại byte giống hệt; file artifact thường được lưu theo checksum |
| **Binary metadata store** | Kết quả resolve dynamic version, module metadata, artifact metadata, con đường dẫn tới artifact đã tải, kết quả không tìm thấy | Giảm tra cứu từ repository và giữ quyết định resolution nhất quán trong TTL |

Một đường dẫn điển hình:

~~~text
GRADLE_USER_HOME/
├── caches/
│   ├── modules-2/
│   │   ├── files-2.1/
│   │   │   └── ... các artifact và metadata theo checksum ...
│   │   └── metadata-2.xxx/
│   │       └── ... chỉ số metadata nội bộ ...
│   ├── build-cache-1/
│   └── ... cache Gradle khác ...
├── wrapper/
│   └── dists/
└── daemon/
    └── ...
~~~

`metadata-2.xxx` là **minh họa tên định dạng nội bộ**; số đuôi phụ thuộc Gradle version, không nên hard-code vào build script hoặc xóa riêng một file index rồi coi đó là API ổn định. `GRADLE_USER_HOME` mặc định thường là `~/.gradle` trên Unix/macOS, nhưng có thể khác nếu người dùng/CI đặt biến môi trường hoặc truyền `--gradle-user-home`.

**Đừng nhầm**:

- `~/.gradle/caches/modules-2`: **dependency cache** (module metadata và downloaded files).
- `~/.gradle/caches/build-cache-1`: local **Build Cache** cho **task outputs**.
- `<project>/.gradle/configuration-cache`: **Configuration Cache** cho trạng thái cấu hình và task graph.
- `<project>/build`: output của build/task.
- `~/.gradle/wrapper/dists`: Gradle distributions được Wrapper tải/cài.

Đây là các cơ chế khác nhau. `--refresh-dependencies` nhắm vào **dependency resolution**, không có nghĩa xóa Build Cache, Configuration Cache, thư mục build hoặc Gradle Wrapper distribution.

### 2.2. Metadata lưu cả câu trả lời “không có”

Giả sử Gradle đã tìm `com.example:does-not-exist:1.0` tại repository A và nhận kết quả không tồn tại. Metadata cache có thể lưu **negative lookup** này để không gửi đi gửi lại cùng yêu cầu vô ích. Nếu sau đó artifact mới được publish với chính tọa độ trên, một lần resolve bình thường có thể vẫn dựa vào kết quả âm đang được cache. Kiểm tra bằng `--refresh-dependencies` có thể giúp buộc Gradle tra cứu lại **repository đã cấu hình**.

Nhưng refresh **không biến tọa độ sai thành đúng** và không khắc phục lỗi quyền truy cập hay repository thiếu artifact. Luôn kiểm tra:

1. Group/module/version có đúng không?
2. Repository nào thực sự chứa artifact?
3. CI có đủ credentials/proxy/truststore không?
4. Module có metadata phù hợp loại repository Maven/Ivy không?
5. Gradle có đang được chạy với `--offline` không?

Không gán một TTL “24 giờ cho mọi kết quả không tồn tại” như quy luật tuyệt đối: độ tồn tại và hạn dùng của các entry phụ thuộc loại metadata, chiến lược resolution và hoàn cảnh. Hai TTL mặc định cần nhớ ở phần sau là cho **dynamic version** và **changing module**.

### 2.3. Cache metadata theo repository và “sticky repository”

Gradle không lưu metadata như một bảng chung bỏ qua nguồn. Metadata cache được tổ chức **theo repository**, với repository được nhận diện bởi các thuộc tính như **URL, loại và layout**. Khi một module đã được resolve từ repository cụ thể, Gradle giữ quan hệ nguồn đó (**repository stickiness**) để giảm rủi ro cùng một tọa độ bất ngờ được thay bằng nội dung của repository khác.

Ví dụ project dùng:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.example.org/releases')
    }
    mavenCentral()
}
~~~

Đây chỉ là **đoạn cấu hình minh họa**; URL `repo.example.org` không phải repository để chạy thử. Nếu module trước đó đến từ repository nội bộ, Gradle không tự tùy tiện chuyển nó sang Maven Central khi nội bộ thiếu hoặc tạm hỏng. Thay URL, đổi thứ tự repo, thay môi trường CI hoặc credentials có thể tạo khác biệt về resolution; `--refresh-dependencies` không thay thế việc xác định đúng nguồn artifact.

**File store có thể tái sử dụng cùng byte** nếu checksum trùng, nhưng **metadata và quan hệ nguồn** vẫn có ranh giới theo repository. Đây là một trong những lý do “tôi nhìn thấy file trong cache” không đồng nghĩa “Gradle sẽ dùng nó cho mọi cấu hình/repository”.

## 3. Ba loại version: fixed, dynamic và changing

Đừng đồng nhất **dynamic version** với **changing module**. Chúng mô tả **hai loại biến động khác nhau**.

| Loại | Ví dụ | Điều có thể thay đổi | Gradle cần cache gì? |
| --- | --- | --- | --- |
| **Fixed, non-changing** | `3.17.0` | Theo quy ước release đúng đắn, nội dung cùng version **không nên đổi** | Module metadata/artifact; không định kỳ xem nó như bản publish mới có cùng version |
| **Dynamic version** | `3.+`, `latest.release` | **Version cụ thể được chọn** có thể đổi khi có release mới | Kết quả map yêu cầu động → version cụ thể |
| **Changing module** | `1.0-SNAPSHOT`, hoặc `1.0` đánh dấu `changing = true` | **Nội dung/metadata của chính version đó** có thể bị xuất bản lại | Module metadata và artifacts của selected version |

Ví dụ minh họa:

~~~groovy
dependencies {
    // Fixed release: phụ thuộc cụ thể và nên bất biến.
    implementation 'org.apache.commons:commons-lang3:3.17.0'

    // Dynamic selector: Gradle chọn một version 3.x phù hợp.
    // Chỉ dùng khi bạn chủ động chấp nhận kết quả thay đổi theo thời gian.
    // implementation 'org.apache.commons:commons-lang3:3.+'

    // Maven SNAPSHOT: tọa độ này được Gradle nhận là changing.
    // Cần artifact thật trong repository tương ứng.
    // implementation 'com.example:internal-lib:1.0-SNAPSHOT'
}
~~~

Hai dòng comment là **tùy chọn thay thế**, không phải ba dependency cùng tên cần bật đồng thời. `3.+` có thể chọn release khác ở lần resolve tương lai; nhưng **một release được chọn không mặc nhiên là changing** chỉ vì selector của nó động. Ngược lại, `1.0-SNAPSHOT` là một tọa độ cố định về tên version, nhưng **nội dung version đó có thể thay đổi**.

### 3.1. Fixed version không bảo đảm build hoàn toàn tái lập

Pin `3.17.0` tốt hơn version động cho khả năng tái lập, nhưng build vẫn có thể biến động nếu:

- Artifact ở một repository bị **republish trái quy ước** dưới cùng version.
- Repository/metadata hoặc variant selection khác giữa máy dev và CI.
- Một dependency bắc cầu sử dụng selector động hoặc changing module.
- Plugin/build script dependency có version động.
- Task lấy đầu vào từ môi trường hoặc dịch vụ bên ngoài.

Với phát hành production, nên kết hợp fixed versions với **dependency locking** (lưu selected versions), **dependency verification** (checksum/signature/trust rules phù hợp), repository policy và CI tests. Locking version không thay thế verification byte, và verification không tự khóa selected version.

### 3.2. Dynamic version là kết quả chọn, không phải một file JAR “3.+”

Khi ghi:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.+'
}
~~~

Gradle cần tìm các version có thể chấp nhận trong repository rồi **chọn một version cụ thể**, ví dụ một release thuộc nhánh 3. Kết quả của việc chọn có thể được **cache trong 24 giờ theo mặc định**. Trong thời gian cache còn hợp lệ, release mới xuất hiện trên server chưa chắc làm Gradle chọn lại ngay.

Mốc 24 giờ ở đây áp dụng cho **kết quả resolve dynamic selector**. Nó **không có nghĩa** mọi JAR cố định được tải lại sau mỗi 24 giờ.

### 3.3. Changing module giữ nguyên tọa độ, nhưng artifact có thể thay

Tại repository nội bộ, đội phát triển có thể publish nhiều lần:

~~~text
com.example:payment-client:2.0-SNAPSHOT
Lần publish 1  -> JAR chứa implementation A
Lần publish 2  -> JAR chứa implementation B
(Tọa độ Gradle yêu cầu vẫn là payment-client:2.0-SNAPSHOT)
~~~

Gradle cần kiểm tra xem **metadata và artifacts của module được đánh dấu changing** đã thay đổi hay chưa. Theo mặc định, thông tin này được **cache 24 giờ**; trong TTL, build có thể dùng bản đã có dù server đã publish lại.

**Snapshot là cơ chế dành cho phát triển/chia sẻ bản chưa ổn định**, không phải một cách quản lý releases dài hạn. Đối với Maven repository, tên kết thúc bằng `-SNAPSHOT` được Gradle xem là changing. Nhưng nếu nhà phát hành republish một version thường như `2.0`, Gradle **không tự biết đây là changing**; người tiêu thụ có thể phải đánh dấu `changing = true` hoặc — tốt hơn — sửa quy trình publish để mỗi release có version bất biến.

## 4. Cách khai báo changing dependency trong Groovy DSL

Với một Maven SNAPSHOT được publish đúng:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.company.example/snapshots')
        // Ví dụ URL nội bộ, cần thay bằng repository thực tế.
    }
}

dependencies {
    implementation 'com.example:payment-client:2.0-SNAPSHOT'
}
~~~

Gradle tự nhận version `-SNAPSHOT` là changing theo cách Maven resolution thông dụng. Đây là **trích đoạn phụ thuộc vào repository nội bộ tồn tại thật**, không phải demo chạy công khai. Không thể chạy nó chỉ với Maven Central nếu artifact không được publish ở đó.

Nếu một module **không có hậu tố SNAPSHOT** nhưng thực tế bị republish cùng version, có thể đánh dấu:

~~~groovy
dependencies {
    implementation('com.example:payment-client:2.0') {
        changing = true
    }
}
~~~

`changing = true` là thuộc tính của **dependency declaration**. Nó yêu cầu Gradle coi nội dung module này có khả năng thay đổi theo thời gian, không đổi tọa độ yêu cầu từ `2.0` thành một selector động.

**Không dùng `changing = true` như cách sửa mọi lỗi**. Nó tăng khả năng recheck remote metadata/artifact, giảm hiệu quả cache và vẫn không giải quyết một repository không chứa module, sai group/name/version hoặc credentials hết hạn. Với artifact release đúng quy trình, giữ version bất biến và publish version mới là tốt nhất.

### 4.1. Nếu metadata thay đổi nhưng JAR vẫn giống nhau

Với changing module, có thể có hai dạng thay đổi độc lập:

- POM/Gradle Module Metadata thêm/bớt **dependency bắc cầu** hoặc thay variant/attributes.
- Artifact JAR thay byte trong khi tọa độ vẫn giữ.

Gradle cần kiểm tra cả thông tin module lẫn artifact mà configuration thực sự cần. Vì thế **chỉ nhìn timestamp của một JAR** chưa đủ để xác nhận graph dependency đã mới. Sau khi refresh, nên kiểm tra `dependencies`/`dependencyInsight` và thực tế classpath/task output.

### 4.2. Snapshot và timestamped Maven snapshots

Một Maven snapshot repository có thể publish artifact dạng timestamped snapshot cùng metadata `maven-metadata.xml` để xác định bản snapshot hiện tại. Trên phía người dùng, Gradle vẫn có thể được yêu cầu bằng tọa độ `2.0-SNAPSHOT`; repository metadata giúp tìm bản tương ứng. Cách server giữ/xóa bản cũ, quyền truy cập và retention policy là vấn đề của repository manager.

Nếu repository quản lý snapshot sai metadata, chỉ tăng TTL hoặc xóa cache không sửa được dữ liệu nguồn. Kiểm tra bằng công cụ repository hoặc yêu cầu người quản trị xác nhận bản publish và metadata trước khi chỉnh build.

## 5. Hai TTL khác nhau: `cacheDynamicVersionsFor` và `cacheChangingModulesFor`

Gradle cung cấp hai phương thức của `ResolutionStrategy`:

| API | Đối tượng hết hạn | Mặc định | Ví dụ sử dụng |
| --- | --- | --- | --- |
| `cacheDynamicVersionsFor` | Mapping dynamic selector → selected version, ví dụ `3.+` → `3.17.0` | **24 giờ** | Muốn kiểm tra release mới mỗi 10 phút |
| `cacheChangingModulesFor` | Cached metadata/artifacts của **module changing**, ví dụ `2.0-SNAPSHOT` | **24 giờ** | Muốn cập nhật snapshots mỗi 5 phút |

Ví dụ Groovy DSL đầy đủ có thể thêm vào `build.gradle` của một project Java:

~~~groovy
configurations.configureEach {
    resolutionStrategy {
        cacheDynamicVersionsFor 10, 'minutes'
        cacheChangingModulesFor 5, 'minutes'
    }
}
~~~

Giải thích:

- `configurations.configureEach` cấu hình các configuration thuộc project khi cần, không ép tất cả configurations resolve ngay.
- `resolutionStrategy` là chính sách resolution cho mỗi configuration.
- `cacheDynamicVersionsFor 10, 'minutes'` điều khiển thời gian dùng lại kết quả chọn version động.
- `cacheChangingModulesFor 5, 'minutes'` điều khiển thời gian dùng lại metadata/artifacts của module changing.
- Cả hai là chính sách của **project configurations đang cấu hình**, không nên suy rằng nó tự thay TTL của mọi plugin/buildscript dependency hoặc mọi included build.

**Đừng đảo hai API**. Đối với `1.0-SNAPSHOT`, muốn recheck **nội dung của một version** thì `cacheChangingModulesFor` là API quan trọng. Đối với `3.+` muốn xem có release mới hay chưa thì `cacheDynamicVersionsFor` mới là API tương ứng.

### 5.1. TTL bằng 0 có nghĩa gì?

Có thể dùng:

~~~groovy
configurations.configureEach {
    resolutionStrategy {
        cacheDynamicVersionsFor 0, 'seconds'
        cacheChangingModulesFor 0, 'seconds'
    }
}
~~~

TTL 0 khiến các kết quả thuộc loại này **hết hạn ngay và thường cần revalidate mỗi lần resolution**, thuận tiện trong một môi trường phát triển snapshot đặc thù. Nó **không phải lệnh xóa toàn bộ cache**, cũng không bắt mọi JAR fixed version tải lại. Revalidation có thể chỉ cần kiểm tra metadata/checksum trên server và tái sử dụng byte đã có.

Đừng cấu hình TTL 0 trên tất cả modules ở CI chỉ để “cho chắc”: nó tăng yêu cầu mạng và độ trễ, đồng thời khiến build nhạy với repository outage. Thường nên giới hạn chính sách vào configurations cần thiết, hoặc thay bằng phát hành snapshot có version/commit rõ hơn.

### 5.2. TTL khác nghĩa “Gradle chắc chắn download sau N phút”

Khi một entry hết hạn:

1. Gradle **có thể truy cập repository** để xác minh còn bản đó hay đã có bản mới.
2. Nếu metadata/artifact không đổi, Gradle có thể giữ dữ liệu/JAR cũ đã tải.
3. Nếu repo không truy cập được, resolution có thể thất bại tùy metadata/cache và mode.
4. Nếu không có task cần resolve configuration, chưa chắc Gradle đã liên hệ server dù thời gian TTL đã trôi qua.

TTL kiểm soát **khi nào cần kiểm tra lại** trong một lần resolution, không phải bộ hẹn giờ tự tải dependency dưới nền khi bạn không chạy Gradle.

## 6. Offline mode: `--offline` thực sự làm gì?

Lệnh:

~~~bash
./gradlew --offline build
./gradlew --offline dependencies --configuration runtimeClasspath
~~~

bật **offline dependency resolution**: Gradle dùng cached modules/metadata/artifacts, **không truy cập mạng để resolve dependency**. Nếu cache chưa có đủ thông tin hoặc artifact cần thiết, build thường **thất bại** thay vì tự tải thêm.

Nó không có nghĩa:

- “Dù chưa từng tải dependency cũng chạy được.”
- “Gradle sẽ dùng một JAR bất kỳ có cùng tên được tìm thấy trên đĩa.”
- “Tất cả task và plugin bị cấm truy cập mạng”: task tùy chỉnh, lệnh `Exec`, test, tool ngoài vẫn **có thể tự truy cập mạng**, vì `--offline` không phải firewall của hệ điều hành.
- “Wrapper sẽ không cần tải Gradle distribution”: Wrapper phải có distribution đã được chuẩn bị; `--offline` không tự làm thư mục `wrapper/dists` xuất hiện.
- “Gradle toolchain auto-provisioning chắc chắn hoạt động offline”: nếu cần tải JDK mới, bạn phải chuẩn bị trước.

**Điều kiện offline thành công:** Gradle distribution, JDK/toolchain, plugin artifacts và mọi dependency graph/task cần dùng đã được chuẩn bị/cached phù hợp. Một build từng chạy `help` online không chứng minh `compileJava` hoặc `test` đã có toàn bộ JAR cần thiết.

### 6.1. Quy trình warm cache trước khi làm việc offline

Trên một máy có mạng, trong project demo ở mục 8:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew build
~~~

Sau khi các artifact cần thiết đã tải thành công, thử:

~~~bash
./gradlew --offline build
./gradlew --offline dependencies --configuration runtimeClasspath
~~~

Nếu chạy được, điều đó chỉ chứng minh **graph và các thao tác đã thực hiện** có đủ dữ liệu trong cache hiện tại. Thêm plugin, thêm dependency test mới, đổi Java toolchain hoặc đổi Gradle version có thể lại cần kết nối mạng.

### 6.2. Không dùng offline để “chữa” repository error mãi mãi

Nếu dependency cache cũ có bản module, `--offline` có thể giúp làm việc tạm thời khi repository bị lỗi. Nhưng kết quả có thể **cũ** đối với dynamic/changing dependency và không được xác nhận là phiên bản mới nhất trên server.

Khi mạng trở lại, dùng resolution bình thường hoặc `--refresh-dependencies` khi cần kiểm tra cập nhật. Nếu build thật sự phải tái lập trong tình huống mất mạng, **pin versions, locking/verification và chuẩn bị offline cache** quan trọng hơn bật offline một cách tùy hứng.

### 6.3. Offline với repository thay đổi

Nếu đổi từ repository A sang B, metadata gắn với A không tự trở thành metadata hợp lệ của B. Một Maven artifact file có sẵn trong file store có thể được Gradle tái sử dụng khi đủ checksum/thông tin tương ứng, nhưng **offline resolve vẫn có thể fail** vì B chưa có entry metadata cần thiết. Đây là hành vi liên quan repository isolation/stickiness, không phải Gradle “không thấy file JAR”.

## 7. `--refresh-dependencies`: revalidate, không phải xóa cache

Lệnh:

~~~bash
./gradlew --refresh-dependencies build
./gradlew --refresh-dependencies dependencies --configuration runtimeClasspath
~~~

nói với Gradle rằng trong lần invocation này, **đừng chỉ tin các kết quả dependency resolution đã cache**; cần kiểm tra lại nguồn repository cho những dependency được resolve. Điều này hữu ích khi:

- Module changing/SNAPSHOT đã được publish lại, bạn muốn xem nội dung mới trước khi TTL hết.
- Dynamic selector có thể chọn release mới hơn.
- Metadata cache vẫn ghi nhận “không có artifact” nhưng artifact vừa được publish.
- Repository proxy hoặc metadata đã được sửa và bạn muốn kiểm chứng lại.

**Điểm rất quan trọng:** `--refresh-dependencies` **không bắt buộc tải lại mọi JAR**. Gradle có thể dùng HTTP HEAD requests, checksum hoặc thông tin tương đương để xác nhận file đang cache **không đổi** rồi tái sử dụng. Việc có nhiều HTTP requests không đồng nghĩa có nhiều lần chuyển toàn bộ byte JAR.

Cờ này cũng **không tự xóa** nội dung của `$GRADLE_USER_HOME/caches`, không thay cấu hình `repositories`, không sửa version sai, không làm plugin thiếu artifact bỗng tồn tại, và không bảo đảm test/build logic có khả năng chạy offline.

### 7.1. Refresh là hành động cho một invocation, TTL là chính sách lâu dài

| Nhu cầu | Lựa chọn |
| --- | --- |
| Thử xem bản SNAPSHOT vừa publish đã cập nhật chưa | Chạy một lần với `--refresh-dependencies` |
| Mỗi ngày CI muốn tự cập nhật dynamic selector sau vài giờ | Cấu hình TTL thích hợp hoặc dùng locking/fixed versions |
| Người dùng cần làm việc không có mạng | `--offline` với cache đã chuẩn bị |
| Library release đã được nâng version rõ trong build.gradle | Dùng build bình thường; refresh chỉ khi nghi metadata/cache cũ |
| Chạy lại toàn bộ task dù output được coi là up-to-date | `--rerun-tasks`, **khác refresh dependencies** |
| Xóa output đã được task tạo dưới `build/` | Task `clean` hoặc xóa output có kiểm soát, **khác refresh dependencies** |

Không kết hợp `--offline` và `--refresh-dependencies` như một “mẹo thần kỳ”: chúng hướng tới **hai mục tiêu đối lập** (không truy cập repository và ép revalidate repository). Chọn một theo mục đích, đừng dùng chung rồi kỳ vọng vừa có bản mới vừa tuyệt đối không cần mạng.

### 7.2. Refresh khi dependency sai tọa độ có ích không?

Không. Nếu project yêu cầu:

~~~groovy
dependencies {
    implementation 'example.nonexistent:wrong-name:999.0'
}
~~~

và không repository nào xuất bản tọa độ đó, `--refresh-dependencies` vẫn fail. Nó chỉ buộc kiểm tra lại, không tự suy ra đúng tên module hoặc thay credentials. Khi gặp lỗi resolution, đọc phần **repositories searched**, HTTP status, missing metadata/variant và tọa độ trước.

### 7.3. Refresh và Changing flag có vai trò khác nhau

Nếu một module bị republish nhiều lần dưới cùng release version `1.0` nhưng Gradle coi là fixed, một lần `--refresh-dependencies` có thể giúp cập nhật. Tuy nhiên, dựa vào refresh thủ công ở mọi máy không phải quy trình phát hành tốt. Nên:

- **Ưu tiên publish version bất biến**, ví dụ `1.0.1` hoặc version gắn commit.
- Nếu bắt buộc thay nội dung cùng version, đánh dấu dependency là `changing` và chọn TTL phù hợp trong môi trường phát triển.
- Khi lên production, cố định phiên bản/artifact bằng locking và verification; tránh dùng moving target mà không kiểm soát.

## 8. Demo hoàn chỉnh Java 17: quan sát cache với dependency cố định

Demo sau **chạy được** với Gradle Wrapper tương thích, JDK 17 được Gradle phát hiện (hoặc đã có toolchain resolver) và mạng truy cập Maven Central ở lần tải đầu. Nó không yêu cầu bạn tự publish library. Mục đích là luyện hai cờ CLI mà **không làm thay đổi dependency theo thời gian**.

### 8.1. Cấu trúc dự án

~~~text
dependency-cache-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    └── main/
        └── java/
            └── demo/
                └── CacheDemo.java
~~~

Đây là cấu trúc của một project **đã có Gradle Wrapper hợp lệ**. File `gradle-wrapper.jar` và `gradle-wrapper.properties` phải được tạo đúng quy trình; không thay thế bằng file rỗng.

### 8.2. `settings.gradle`

~~~groovy
rootProject.name = 'dependency-cache-demo'
~~~

### 8.3. `build.gradle`

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    // Fixed release: cố ý không dùng SNAPSHOT hoặc version động.
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.CacheDemo'
}
~~~

Giải thích:

- Application plugin tạo task `run`, `installDist`, `distZip` và các task Java liên quan; không cần thêm version cho core plugin.
- `mavenCentral()` là repository cho project dependency (khác với plugin resolution của external plugin).
- `implementation` đưa Commons Lang3 vào compile/runtime classpath của mã Java.
- `3.17.0` là version cố định, giúp output thực hành không thay khi có release mới.
- `java.toolchain` chọn JDK 17 cho các task Java hỗ trợ; không tự thay đổi JVM chạy Gradle Daemon.

### 8.4. `src/main/java/demo/CacheDemo.java`

~~~java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class CacheDemo {
    private CacheDemo() {
    }

    public static void main(String[] args) {
        String input = args.length == 0 ? "Gradle" : args[0];
        System.out.println("reverse=" + StringUtils.reverse(input));
    }
}
~~~

Đây là chương trình Java 17 hoàn chỉnh. Public class `CacheDemo` nằm trong file `CacheDemo.java` và package `demo`. `StringUtils` yêu cầu Commons Lang JAR trên classpath. Nếu biên dịch bằng lệnh `javac` độc lập, bạn phải cung cấp JAR đó qua `-cp`; Gradle sẽ tự làm nhờ `implementation`.

### 8.5. Lần đầu tải dependency và chạy app

Trên Linux/macOS, tại root project:

~~~bash
./gradlew -q run
./gradlew -q run --args='Hello'
~~~

Stdout của Java main cho hai lần chạy lần lượt:

~~~text
reverse=eldarG
~~~

và:

~~~text
reverse=olleH
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat -q run
.\gradlew.bat -q run --args="Hello"
~~~

Hai chuỗi là kết quả **chính xác** của `StringUtils.reverse` với ASCII input `Gradle` và `Hello`. Gradle hoặc JDK vẫn có thể in cảnh báo/metadata riêng tùy môi trường; ở đây chỉ mô tả stdout do `CacheDemo.main` tạo ra.

### 8.6. Xem đồ thị dependency rồi thử offline

~~~bash
./gradlew -q dependencies --configuration runtimeClasspath
./gradlew -q dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath

./gradlew --offline -q run
./gradlew --offline -q dependencies --configuration runtimeClasspath
~~~

Nếu trước đó `run` và resolution thành công, và **Wrapper distribution/JDK/plugin dependencies cần thiết còn sẵn**, các lệnh offline thường sẽ thành công. Đây là cách kiểm tra đủ cache cho **đúng graph**. Nếu một lệnh offline thất bại, đọc thông báo thiếu module/metadata/file; không kết luận Gradle chưa cache bất kỳ file gì.

Không cần chạy `clean` để chứng minh metadata cache hoạt động. `clean` xóa output project; nó không kiểm soát cache dependency của Gradle User Home.

### 8.7. Refresh và quan sát mạng

~~~bash
./gradlew --refresh-dependencies --info dependencies --configuration runtimeClasspath
./gradlew --refresh-dependencies -q run
~~~

Đọc `--info` để xem Gradle có kiểm tra metadata/repository hoặc tái sử dụng artifact nào. Log cụ thể phụ thuộc Gradle version, server, proxy và trạng thái cache; **không có stdout HTTP cố định** để khẳng định trước. Vì Commons Lang `3.17.0` trong demo là release cố định, nếu repository không thay đổi, việc refresh thường **không đổi version hoặc output Java**.

Một quan sát hợp lý:

| Lần chạy | Kỳ vọng về resolution | Kỳ vọng output chương trình |
| --- | --- | --- |
| Lần đầu online, cache chưa có | Có thể cần tải metadata và JAR | `reverse=eldarG` |
| Online lần sau, cache hợp lệ | Tái dùng metadata/file, ít network hơn | `reverse=eldarG` |
| Offline sau khi warm cache | Không truy cập mạng để resolve dependency | `reverse=eldarG` |
| Refresh sau khi warm cache | Revalidate nguồn; có thể không tải lại JAR | `reverse=eldarG` |

Không dùng dung lượng file download hay số lượng request làm tiêu chí duy nhất: một proxy/caching repository có thể phản hồi khác nhau trong khi selected dependency vẫn giống.

### 8.8. So sánh với chạy Java độc lập

Nếu đã có Commons Lang JAR trên máy (ví dụ bạn lấy đúng file từ repository), có thể thử:

~~~bash
# Linux/macOS: LANG_JAR là đường dẫn tới commons-lang3-3.17.0.jar.
javac -cp "$LANG_JAR" -d out src/main/java/demo/CacheDemo.java
java -cp "out:$LANG_JAR" demo.CacheDemo Hi
~~~

Output:

~~~text
reverse=iH
~~~

Trên Windows, separator của classpath là dấu `;` thay vì `:`. Đây là **thí nghiệm tùy chọn**; nếu biến `LANG_JAR` chưa trỏ tới JAR hợp lệ, lệnh `javac` không thể tìm `StringUtils`. Dùng Wrapper là cách được khuyến nghị vì nó quản lý classpath và transitive dependencies tự động.

## 9. Thí nghiệm riêng: dynamic version và TTL chọn version

Để quan sát **cacheDynamicVersionsFor**, thay dependency Commons Lang **trong bản sao demo**:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.+'
}
~~~

Và thêm (ở ngoài khối `dependencies`):

~~~groovy
configurations.configureEach {
    resolutionStrategy {
        cacheDynamicVersionsFor 10, 'minutes'
    }
}
~~~

Đây là **phương án thực nghiệm thay thế**, không phải cấu hình cần dán đè lên `build.gradle` chính mà không xóa dòng dependency cũ.

Chạy:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew --refresh-dependencies dependencies --configuration runtimeClasspath
~~~

Trong report, tìm mũi tên tương tự:

~~~text
org.apache.commons:commons-lang3:3.+ -> 3.x.y
~~~

`3.x.y` ở đây là **ký hiệu phiên bản được chọn tại thời điểm chạy**, không phải output literal. Không viết cứng một version cụ thể vì Maven Central có thể có release mới sau khi bài được viết.

Điểm cần giải thích:

1. `3.+` yêu cầu một version phù hợp nhánh 3, không pin một con số.
2. Gradle cache **selected version** cho dynamic selector trong TTL, mặc định 24 giờ nếu không override.
3. Khi TTL hết hoặc dùng `--refresh-dependencies`, Gradle có thể kiểm tra repository để xem bản mới.
4. Nếu không có release mới, selected version vẫn có thể giữ nguyên. **“Refresh” không có nghĩa bắt buộc chọn version khác**.
5. Nếu muốn build tái lập, chuyển về version cố định/locking sau khi xác định version cần dùng.

Đây là thí nghiệm quan sát dynamic version. Nó **không trực tiếp minh họa JAR SNAPSHOT bị thay nội dung dưới cùng version**.

## 10. Thí nghiệm riêng: changing module trong repository nội bộ

Không có một Maven SNAPSHOT công khai nào có thể **cam kết thay nội dung theo giờ** để tạo stdout cố định. Vì vậy ví dụ sau là **quy trình kiểm nghiệm** dành cho nhóm có repository Maven/Ivy thử nghiệm và quyền publish.

### 10.1. Thiết lập tình huống

Giả sử nhóm có một module:

~~~text
Repository: https://repo.company.example/snapshots
Module:     com.example:demo-util:1.0-SNAPSHOT
Publish A:  method describe() trả "A"
Publish B:  method describe() trả "B"
~~~

Dấu tên miền/repository ở đây chỉ minh họa; không được coi là endpoint có sẵn.

Trong `build.gradle` của consumer:

~~~groovy
plugins {
    id 'java'
}

repositories {
    maven {
        url = uri('https://repo.company.example/snapshots')
        // Đặt credentials qua CI/secret provider nếu repo yêu cầu.
    }
}

dependencies {
    implementation 'com.example:demo-util:1.0-SNAPSHOT'
}

configurations.configureEach {
    resolutionStrategy {
        cacheChangingModulesFor 5, 'minutes'
    }
}
~~~

Đây là **trích đoạn đủ để minh họa cấu hình**, nhưng **không standalone chạy được** khi module/repository thử nghiệm chưa tồn tại; đó là giới hạn rõ ràng của thí nghiệm publish.

### 10.2. Thứ tự kiểm chứng

1. Publish bản A dưới version `1.0-SNAPSHOT`, kiểm tra server xác nhận metadata/artifact của bản này.
2. Chạy consumer online để tải/resolve A, ghi lại selected module và checksum/file nếu công cụ repository cho phép.
3. Publish bản B **cùng SNAPSHOT coordinate**, xác nhận server metadata đã cập nhật.
4. Chạy lại consumer trong thời gian TTL. Nếu metadata cache còn hiệu lực, Gradle có thể vẫn dùng A.
5. Chạy consumer với `--refresh-dependencies`, so sánh output và resolved file sau khi revalidate.
6. Thử `--offline` sau khi cache A hoặc B đã có; xác định nó dùng bản được cache, **không tìm bản mới từ server**.
7. Hoàn trả repository/demo về trạng thái thử nghiệm; không republish release production cố định để làm ví dụ.

Trong một trường hợp thực tế, Gradle có thể sử dụng snapshot timestamped và metadata do repository manager cung cấp. Nếu server chặn HEAD, có proxy/CDN cache riêng hoặc publish chưa hoàn tất, kết quả cần được kiểm chứng từ server chứ không suy đoán chỉ dựa vào cờ Gradle.

### 10.3. Thử changing version không có hậu tố SNAPSHOT

Nếu tổ chức buộc publish lại `1.0` cùng tọa độ (không khuyến nghị), consumer phải khai báo:

~~~groovy
dependencies {
    implementation('com.example:demo-util:1.0') {
        changing = true
    }
}
~~~

Khi đó `cacheChangingModulesFor` điều chỉnh kỳ hạn recheck. Tuy nhiên, quy trình quản lý release tốt hơn là publish `1.0.1`, tránh rủi ro đồng nhất sai giữa máy dev, CI và production.

## 11. Chẩn đoán cache bằng lệnh và log

### 11.1. Bộ lệnh thường dùng

~~~bash
# Đảm bảo đang dùng đúng Wrapper/Gradle version:
./gradlew --version

# Xem dependency graph của app:
./gradlew dependencies --configuration runtimeClasspath

# Vì sao một module được chọn:
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath

# Thử dùng cache, không hỏi repository:
./gradlew --offline dependencies --configuration runtimeClasspath

# Kiểm tra lại repository/cache metadata:
./gradlew --refresh-dependencies --info dependencies --configuration runtimeClasspath
~~~

Chỉ chạy những configuration thực sự tồn tại trong project; `runtimeClasspath` thường đến từ Java/Application plugin. Với multi-project, dùng:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
~~~

Report của root project **không tự thay thế** report của `:app`. Nếu root chỉ cấu hình các subproject mà không áp dụng Java plugin, nó có thể không có `runtimeClasspath`.

### 11.2. `--info` và `--debug`

`--info` có thể hiển thị thêm thông tin về dependency resolution, repository requests và cache usage. `--debug` chi tiết hơn nhưng log rất lớn và **có thể chứa thông tin nhạy cảm từ môi trường**; chỉ bật khi thật cần, kiểm soát nơi lưu log và loại bỏ secret trước khi chia sẻ.

Mẫu phân tích:

| Quan sát | Diễn giải có thể | Không nên kết luận vội |
| --- | --- | --- |
| Log nói dùng file từ cache | Artifact bytes có thể được reuse | Mọi metadata/repository đều đã fresh |
| Có HTTP HEAD/metadata request | Gradle revalidate cache entry | Chắc chắn JAR được tải lại |
| Có version arrow `1.+ -> 1.4` | Dynamic selector được resolve thành version cụ thể | Version luôn là 1.4 ở mọi máy/thời điểm |
| Cache hit ở Configuration Cache | Gradle có thể bỏ qua pha configuration | Dependency cache luôn là bản mới nhất |
| Task `UP-TO-DATE` | Task inputs/outputs chưa cần chạy lại | Không có repository lookup nào đã xảy ra |
| Offline fail vì artifact/metadata missing | Cache chưa đủ cho graph này | Các JAR khác trong cache đều hỏng |
| Refresh vẫn chọn version cũ | Repository chưa có bản mới, selector/constraint giữ version hoặc metadata nguồn chưa cập nhật | Cờ refresh bị Gradle bỏ qua |

### 11.3. Cách xem selected version

Ví dụ:

~~~bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
~~~

Khi dùng version động, output report cho bạn **selected version tại thời điểm resolution** và các dependency paths. Khi dùng SNAPSHOT, report thường vẫn hiển thị tọa độ `1.0-SNAPSHOT` chứ không chứng minh **byte artifact** mới hay cũ; để kiểm tra nội dung thực sự, cần so checksum/artifact hoặc chạy test đối chiếu có đầu vào xác định.

### 11.4. Cache hỏng và việc xóa thủ công

Nếu nghi local cache corrupted, trước tiên thử:

1. Kiểm version/repository/credentials.
2. Chạy một lần với `--refresh-dependencies`.
3. Kiểm tra lỗi thật, checksum/verification.
4. So sánh với môi trường sạch **có kiểm soát**, ví dụ một `GRADLE_USER_HOME` tạm dành cho demo.

Không tự xóa toàn bộ `~/.gradle` trên máy phát triển hay runner đang dùng chung: bạn có thể làm mất wrapper distributions, caches khác, settings và khiến nhiều project phải tải lại. Khi cần thử bằng một user home riêng, Unix/macOS có thể dùng:

~~~bash
mkdir -p /tmp/gradle-cache-test
GRADLE_USER_HOME=/tmp/gradle-cache-test ./gradlew --version
GRADLE_USER_HOME=/tmp/gradle-cache-test ./gradlew dependencies --configuration runtimeClasspath
~~~

Đây là **thí nghiệm cô lập**, không phải lệnh “sửa” bắt buộc. Home mới chưa có Wrapper/metadata nên lần đầu vẫn có thể phải tải distribution và dependency. Trên Windows PowerShell, có thể dùng `$env:GRADLE_USER_HOME = 'C:\temp\gradle-cache-test'` trong phiên terminal rồi chạy `.\gradlew.bat ...`; nhớ đặt lại environment theo nhu cầu sau đó.

## 12. So sánh với Build Cache và Configuration Cache

| Cơ chế | Lưu gì? | Cách điều khiển thường gặp |
| --- | --- | --- |
| **Dependency cache** | Artifact files, module metadata, version selection, negative lookups | `--offline`, `--refresh-dependencies`, `cacheDynamicVersionsFor`, `cacheChangingModulesFor` |
| **Build Cache** | Output của task cacheable theo input/task implementation | `--build-cache` / `--no-build-cache`, local/remote build cache |
| **Configuration Cache** | Trạng thái configuration/task graph để bỏ qua cấu hình ở cache hit | `--configuration-cache` / `--no-configuration-cache` |
| **Up-to-date checking** | Lịch sử task inputs/outputs để xác định task có cần chạy lại | `--rerun-tasks` để cưỡng bức chạy lại task |
| **Wrapper distribution cache** | Bản Gradle distribution mà Wrapper tải/cài | Cấu hình Wrapper, Gradle version và `GRADLE_USER_HOME` |

Ví dụ một task `compileJava` được `UP-TO-DATE` dù dependency graph đang có một dynamic selector hết TTL. Khi Gradle thực sự cần xác định classpath, nó có thể revalidate dependency metadata để biết liệu task input (resolved classpath) thay đổi hay không. Một lần Configuration Cache hit có thể thay đổi thời điểm Gradle xác định input, nhưng **không có nghĩa hệ thống dependency resolution bị vô hiệu hóa hoàn toàn**.

### 12.1. `clean` không thay `--refresh-dependencies`

~~~bash
./gradlew clean build
~~~

`clean` xóa build outputs (theo task clean/plugin), buộc các task liên quan tái tạo output. Nó **không đảm bảo kiểm tra lại metadata mới ở remote repository**. Nếu muốn kiểm tra snapshot mới theo chủ đích, dùng:

~~~bash
./gradlew --refresh-dependencies build
~~~

Tương tự, `--rerun-tasks` buộc task execution, còn `--refresh-dependencies` là **dependency resolution**. Có thể dùng hai cờ cho hai mục đích riêng biệt khi cần, nhưng không mặc định kết hợp mọi cờ sẽ “chữa” tất cả cache problem.

## 13. CI và ephemeral runners: cache sao cho an toàn

CI thường tạo container/VM mới cho mỗi job; nếu không giữ cache, mỗi job có thể phải tải Gradle distribution và hàng trăm dependencies. Có một số hướng:

1. Dùng CI cache keyed theo OS, phiên bản Gradle, JDK và các file ảnh hưởng dependency declarations/lockfiles.
2. Dùng repository proxy/artifact manager đáng tin để giảm chi phí download và enforce policy.
3. Chuẩn bị Gradle User Home hoặc dependency cache trước cho môi trường offline, với **metadata format tương thích** với Gradle version sử dụng.
4. Dùng **read-only shared dependency cache** theo cơ chế Gradle hỗ trợ nếu nhiều container cần dùng cùng dữ liệu; tránh nhiều tiến trình/container ghi vào một binary metadata cache không được phối hợp.
5. Dùng fixed versions, dependency locking và verification cho release pipeline; giới hạn SNAPSHOT/dynamic versions ở môi trường được chấp nhận.
6. Theo dõi cache hit/miss, metadata revalidations và tốc độ repo trước khi giảm TTL.

### 13.1. Sao chép dependency cache cần lưu ý

Gradle dependency cache có thể được sao chép cho các runner khác nhau, nhưng khi tạo cache snapshot để phân phối:

- Ưu tiên cache `$GRADLE_USER_HOME/caches/modules-2` với metadata và file store phù hợp, **không chỉ một số JAR lẻ**.
- Không copy các file `*.lock` và `gc.properties` khi dựng cache dùng chung theo tài liệu Gradle.
- Đảm bảo Gradle versions sinh/đọc cache tương thích định dạng metadata; một phiên bản Gradle khác có thể cần thêm remote requests để hoàn thiện metadata.
- Không dùng chung cache **ghi được đồng thời** giữa nhiều container không có cơ chế khóa/communication phù hợp.
- Với read-only dependency cache, tuân theo cơ chế chính thức để tách nơi đọc chung và writable cache của mỗi runner.
- Không nhầm cache reuse với **checksum/signature verification**. Kiểm soát nguồn artifact vẫn rất cần thiết.

### 13.2. Chính sách snapshot phù hợp môi trường

| Môi trường | Gợi ý thực tế |
| --- | --- |
| Máy developer tích hợp thay đổi liên tục | Changing snapshots với TTL ngắn có chủ đích; dùng refresh khi publish khẩn |
| CI chạy unit tests hằng ngày | Ưu tiên pinned deps; dùng cache ổn định, không ép refresh toàn bộ nếu không cần |
| Pipeline integration với nội bộ SNAPSHOT | Có thể điều chỉnh `cacheChangingModulesFor` cho configurations liên quan; ghi lại bản artifact/commit |
| Release/production | Tránh mutable coordinates; pin versions, lock dependency graph, verify artifact integrity |
| Air-gapped/offline | Prefetch wrapper, JDK, plugin/dependencies và metadata đúng repository; test `--offline` trước |

Việc để TTL 0 cho mọi configuration ở mọi job thường gây tốn request và tăng khả năng phụ thuộc network; dùng theo nhu cầu, không xem đây là mặc định “an toàn nhất”.

## 14. Lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Đã publish SNAPSHOT mới nhưng build vẫn dùng code cũ | Changing-module TTL còn hiệu lực, server metadata chưa cập nhật hoặc proxy cache | `--refresh-dependencies`, kiểm server metadata/checksum, `dependencyInsight` và test thực tế |
| Dynamic `3.+` không chọn release vừa xuất bản | Dynamic-version selection cache còn hạn, metadata/repo chưa thấy release, constraint giới hạn | `--refresh-dependencies`, xem selected version và constraints |
| `--refresh-dependencies` vẫn không thấy artifact | Sai repo/coordinate/credentials, artifact chưa publish, marker/variant không phù hợp | Xem repositories searched và server; refresh không tự sửa cấu hình |
| Refresh có network requests nhưng JAR không tải lại | Server báo file/checksum giống cache | Đây là revalidation bình thường |
| Offline fail sau lần `help` online | `help` chưa resolve tất cả graphs/artifacts | Warm đúng task/dependencies/plugin và JDK cần thiết |
| Offline fail sau khi đổi `GRADLE_USER_HOME` | Cache thuộc home cũ hoặc Wrapper chưa có distribution ở home mới | Chuẩn bị lại home đúng, đừng giả định cache chia sẻ |
| Offline fail sau khi thêm dependency mới | Cache thiếu metadata/artifact mới | Chạy online trước rồi thử offline |
| Build chậm vì mỗi run đều gọi repo | TTL bị đặt quá ngắn/0, dynamic/changing nhiều, repository nhiều | Tăng TTL, pin versions, giảm số repo, đo `--info` |
| Có JAR trong cache nhưng Gradle không sử dụng | Repository metadata khác, variant/attributes không khớp, graph khác | Kiểm project/configuration/repository stickiness, không copy JAR thủ công |
| Một module đổi repo A sang B mà build khác nhau | Repository-specific metadata và stickiness | Kiểm URL/type/layout, auth, repo order và cache state |
| Fixed release bị republish nhưng Gradle vẫn dùng bản cũ | Gradle coi release là immutable theo quy ước | Xuất version mới; tạm dùng refresh/changing nếu quy trình đặc biệt |
| `clean` không làm dependency được cập nhật | clean xóa build outputs, không ép revalidate resolution | Dùng refresh đúng mục đích |
| `--rerun-tasks` không tải JAR mới | Chạy lại task ≠ refresh dependency cache | Dùng refresh/TTL phù hợp |
| `--no-build-cache` vẫn dùng JAR đã tải | Build Cache khác Dependency Cache | Đây là hành vi bình thường |
| Lỗi checksum sau refresh | Artifact server thay, verification metadata không khớp hoặc nguồn không tin cậy | Kiểm integrity/verification; không tắt security chỉ để chạy được |
| Cache hoạt động trên dev nhưng CI fail | Gradle metadata format/JDK/Wrapper/repo/credentials khác | Pin Wrapper/JDK, chuẩn bị cache đúng, không chia sẻ writable cache không an toàn |
| Repo 401/403 | Thiếu quyền/credentials, không phải cache TTL | Sửa authentication/secret, không chờ TTL |
| Repo 404 sau vừa publish | Publish chưa hoàn tất, sai tọa độ, negative metadata cached | Kiểm server, dùng refresh sau khi xác nhận artifact tồn tại |
| Cảnh báo “configuration cache” dù đang debug dependency | Đây là cache khác, có vi phạm cấu hình riêng | Đọc report Configuration Cache, không chỉ sửa dependency TTL |

### 14.1. Trình tự chẩn đoán hiệu quả

~~~text
1. Lỗi hoặc phiên bản cũ nằm ở Gradle plugin, build script hay app?
                         |
                         v
2. Project/configuration nào đang resolve? :app:runtimeClasspath?
                         |
                         v
3. Loại version: fixed, dynamic (1.+), hay changing (SNAPSHOT)?
                         |
                         v
4. Dependency được resolve từ repository nào?
                         |
                         v
5. Cache TTL nào liên quan? Có đang dùng --offline?
                         |
                         v
6. dependencies + dependencyInsight để xem selected version
                         |
                         v
7. Nếu cần, thử --refresh-dependencies --info đúng invocation
                         |
                         v
8. So metadata/checksum server, repository, credentials và test
                         |
                         v
9. Sửa khai báo/publishing/TTL/CI; xác minh trước và sau
~~~

Không phải lúc nào refresh cũng là bước đầu tiên. Nếu đang nhìn sai project/configuration hoặc plugin resolution khác app dependency, refresh có thể làm tăng request nhưng không cung cấp thông tin mới cần thiết.

## 15. Bài tập thực hành có đáp án gợi ý

### Bài A — phân biệt dynamic với changing

Hai khai báo:

~~~groovy
implementation 'org.apache.commons:commons-lang3:3.+'
implementation 'com.example:toolkit:1.0-SNAPSHOT'
~~~

Đây là **hai dòng minh họa đặt trong `dependencies { }`**, không phải project demo tự chạy được nếu `com.example:toolkit` không tồn tại.

- Dòng 1: **dynamic selector**; Gradle cache mapping `3.+` → selected version. TTL qua `cacheDynamicVersionsFor`.
- Dòng 2: **changing module**; tọa độ version vẫn `1.0-SNAPSHOT` nhưng nội dung có thể đổi. TTL qua `cacheChangingModulesFor`.

### Bài B — 24 giờ là thời gian tải lại JAR?

Câu hỏi: “Gradle mặc định tải lại tất cả JAR mỗi 24 giờ, đúng hay sai?” **Sai.** Hai TTL mặc định 24 giờ gắn với dynamic selection và changing modules. Fixed non-changing modules không phải bị tải lại định kỳ; khi TTL hết, Gradle có thể revalidate chứ không nhất thiết tải lại file nếu unchanged.

### Bài C — offline với cache chưa đủ

Bạn chỉ chạy `./gradlew help` online và sau đó đổi build để thêm một thư viện mới. `./gradlew --offline test` chắc chắn thành công không? **Không.** Cache có thể thiếu metadata, JAR, plugin hoặc test dependencies. Cần warm cache bằng graph/task phù hợp trước.

### Bài D — refresh có xóa cache không?

`./gradlew --refresh-dependencies build` **không tương đương** `rm -rf ~/.gradle/caches`. Nó buộc Gradle xem lại thông tin từ repository và có thể tái sử dụng files giống checksum, trong khi xóa vật lý cache gây nhiều lần download và có thể phá dữ liệu runner khác.

### Bài E — negative cache

Một module vừa được publish sau khi buổi sáng có lỗi 404. Cần kiểm tra điều gì? Tọa độ và repository/credentials trước; khi đã thấy artifact hợp lệ trên server, dùng `--refresh-dependencies` để không chỉ tin negative lookup cũ. Nếu vẫn lỗi, đọc logs và metadata server.

### Bài F — Changing module với version không có SNAPSHOT

Một module nội bộ `com.example:lib:1.0` bị publish lại cùng version mỗi ngày. Gradle mặc định không xem một release thông thường là changing. Muốn tạm hỗ trợ cơ chế này, dùng:

~~~groovy
dependencies {
    implementation('com.example:lib:1.0') {
        changing = true
    }
}
~~~

Về lâu dài, hãy sửa quy trình publish để dùng version bất biến và tránh “phải refresh mới đúng”.

### Bài G — metadata theo repository

Một JAR có sẵn từ repository A, nhưng cấu hình đổi sang B. Offline có chắc chạy không? **Không.** Metadata cho B có thể chưa được cache; Gradle không tự hợp nhất mọi repository chỉ vì file byte giống nhau.

### Bài H — so sánh ba lệnh

Xét:

~~~bash
./gradlew clean build
./gradlew --rerun-tasks build
./gradlew --refresh-dependencies build
~~~

- `clean build`: dọn output rồi tạo lại tasks theo model.
- `--rerun-tasks`: ép task chạy lại thay vì skip do up-to-date.
- `--refresh-dependencies`: bắt kiểm tra lại **dependency resolution**.
  
Ba lệnh có thể gây biểu hiện giống nhau ở một số trường hợp (ví dụ build tốn thời gian hơn), nhưng tác động kỹ thuật **khác nhau**.

### Bài I — thiết kế CI

Nhóm có SNAPSHOT thay đổi mỗi vài phút, CI phải chạy ổn định trong giờ cao điểm. Hãy đưa ra chính sách cân bằng: chỉ giảm changing TTL ở job integration đặc thù; giữ release pipeline pinned; cache Gradle distributions/JDK/dependency modules theo Gradle version; dùng repo proxy; không đặt TTL 0 cho mọi job chỉ vì một module thay đổi.

## 16. Checklist cuối bài

1. **Xác định loại dependency:** fixed release, dynamic selector hay changing module; chúng không đồng nghĩa.
2. **Nhớ hai TTL mặc định:** dynamic version selection **24 giờ**, changing-module metadata/artifacts **24 giờ**.
3. **Dùng đúng ResolutionStrategy API:** `cacheDynamicVersionsFor` cho mapping selector → version; `cacheChangingModulesFor` cho module có nội dung mutable.
4. **Hiểu metadata cache:** có thông tin module, artifact, dynamic selection, negative lookups, timestamp và repository.
5. **Hiểu file cache:** JAR/metadata files thường được lưu theo checksum; reuse file byte không xóa ranh giới giữa repositories.
6. **Dùng `--offline` khi đã chuẩn bị đủ distribution/JDK/plugins/dependencies**, không coi nó là mạng bị chặn cho mọi task.
7. **Dùng `--refresh-dependencies` để revalidate khi cần**, không nghĩ nó xóa cache hoặc luôn tải lại tất cả.
8. **Không dùng `clean` hay `--rerun-tasks` thay cho refresh dependency resolution**.
9. **Chẩn đoán đúng configuration/project** bằng `dependencies`, `dependencyInsight` và logs `--info`.
10. **Tránh republish release cùng version**; dùng snapshot trong môi trường cho phép, fixed/locked/verified dependencies cho production.
11. **Cẩn thận với CI shared cache và repository stickiness**; không sao chép lock files hoặc cùng ghi vào một metadata store không phối hợp.
12. **Luôn ghi lại lệnh, Gradle Wrapper version, repository và thời điểm kiểm tra** khi báo lỗi dependency “cũ”.

## Tài liệu tham khảo chính thức

- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): hai lớp cache, metadata theo repository, changing modules, dynamic version TTL, `--offline`, `--refresh-dependencies` và CI cache.
- [Gradle — ResolutionStrategy API](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/ResolutionStrategy.html): `cacheDynamicVersionsFor`, `cacheChangingModulesFor` và các rules.
- [Gradle — Gradle-Managed Directories and Caches](https://docs.gradle.org/current/userguide/directory_layout.html): `GRADLE_USER_HOME/caches/modules-2` và phân biệt Build Cache/Configuration Cache.
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight` và selected versions.
- [Gradle — Best Practices for Performance](https://docs.gradle.org/current/userguide/performance.html): giảm dynamic/snapshot versions không cần thiết, tối ưu repository requests.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): lưu selected versions để tăng tính tái lập.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum, signature và nguồn dependency.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): giải thích cache của task graph khác dependency cache.
