# Chính sách tệp trùng, quyền truy cập và bảo toàn cấu trúc trong Gradle

## Mục tiêu bài học

Khi Gradle **sao chép tài nguyên**, **đồng bộ thư mục** hoặc **đóng gói ZIP/TAR/JAR**, ba vấn đề quyết định chất lượng kết quả là:

1. **Tệp trùng đích:** hai nguồn có thể cùng tạo một đường dẫn tương đối trong đầu ra; phải quyết định báo lỗi, giữ bản đầu, cho phép nhiều entry hay cảnh báo.
2. **Quyền truy cập:** file cần quyền đọc/ghi nào, script có cần bit thực thi không, quyền của thư mục có khác quyền file không, và archive giữ hay chuẩn hóa quyền từ filesystem?
3. **Cấu trúc thư mục:** tệp nguồn nằm ở cấp nào trong đầu ra, có giữ đường dẫn tương đối, có đổi tên/đổi vị trí, có giữ thư mục rỗng và có vô tình xóa tệp ngoài phạm vi quản lý hay không?

Đây là bài **Gradle file/resource handling**, sử dụng **CopySpec** và các task **Copy**, **Sync**, **Zip** và **Tar**. Ví dụ chính dùng **Groovy DSL** (**build.gradle**), có đối chiếu **Kotlin DSL**. Bài giả định bạn đang dùng một bản Gradle hiện đại; riêng API thiết lập quyền **filePermissions/dirPermissions** có từ Gradle **8.3**. Hãy đối chiếu bản thực tế qua **./gradlew --version**, không áp dụng API mới cho Wrapper quá cũ.

Sau bài học, bạn có thể đọc và thiết kế chính sách **DuplicatesStrategy**, biết cách dùng **from/into**, **include/exclude**, **rename**, **eachFile**, **filePermissions**, **dirPermissions**, **includeEmptyDirs**, và kiểm chứng output mà không đoán từ tên task.

## 1. Phân biệt đường dẫn nguồn và đường dẫn đích

Xem cây thư mục giả định:

~~~text
demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/dist/
    ├── common/
    │   ├── README.txt
    │   ├── conf/app.properties
    │   ├── docs/manual.txt
    │   └── bin/start.sh
    ├── addons/
    │   └── NOTICE.txt
    └── overrides/
        └── conf/app.properties
~~~

Giả sử nội dung tệp như sau:

| Tệp nguồn | Nội dung đơn giản |
| --- | --- |
| **common/README.txt** | **Demo release** |
| **common/conf/app.properties** | **mode=base** |
| **common/docs/manual.txt** | **Read this manual.** |
| **common/bin/start.sh** | **#!/bin/sh** rồi **echo "Started"** |
| **addons/NOTICE.txt** | **Optional notice** |
| **overrides/conf/app.properties** | **mode=override** |

Các tệp này là **fixture thực hành**: bạn cần tạo chúng trước khi chạy lệnh, giữ nguyên đường dẫn. Ví dụ minh họa chính sách, không tự động tạo dữ liệu nguồn và không cần tải thư viện bên ngoài.

### 1.1. from(directory) sao chép nội dung, không tự mang theo tên directory

~~~groovy
tasks.register('copyCommon', Copy) {
    from('src/dist/common')
    into(layout.buildDirectory.dir('copied'))
}
~~~

Hình dạng kết quả sẽ là:

~~~text
build/copied/
├── README.txt
├── conf/app.properties
├── docs/manual.txt
└── bin/start.sh
~~~

**Không** phải **build/copied/common/README.txt**. Khi **from** nhận một thư mục, các tệp con được xem theo **đường dẫn tương đối bên trong thư mục nguồn**. Thành phần **common** là gốc lấy nội dung nên không được tự thêm vào đích.

Nếu muốn giữ một tầng tên **common**, dùng **into** trên child CopySpec:

~~~groovy
tasks.register('copyCommonUnderName', Copy) {
    into(layout.buildDirectory.dir('copied-by-name'))

    from('src/dist/common') {
        into('common')
    }
}
~~~

Kết quả sẽ có **build/copied-by-name/common/README.txt**, **.../common/conf/app.properties** và các tệp con khác. Đây là cách **giữ cấu trúc có chủ đích**, không phải một tùy chọn “preserve everything”.

### 1.2. Cơ chế tính đường dẫn đích

Đối với một file được CopySpec duyệt qua, hãy nghĩ:

~~~text
đường dẫn đích tương đối
  = tiền tố do into(...) của child spec
  + đường dẫn tương đối tính từ from(...)
  + các sửa đổi do rename/eachFile
~~~

Đây là mô hình giải thích, không phải công thức xử lý mọi API. **Hai tệp bị xem là trùng khi sau tất cả phép ánh xạ chúng cùng nhắm tới một đường dẫn đích trong cùng copy/archive operation**, bất kể trước đó chúng nằm ở hai folder nguồn khác nhau.

**Đường dẫn tương đối** khác với đường dẫn tuyệt đối của máy. Đừng thiết kế build phụ thuộc vào một thư mục như **C:\Users\...** hoặc **/home/someone/...** nếu không thực sự cần; ưu tiên **layout.projectDirectory**, **layout.buildDirectory** và Provider từ task sản xuất file.

## 2. CopySpec: nền tảng dùng chung của Copy, Sync và archive

**CopySpec** mô tả nguồn, đích bên trong phép sao chép, lọc, đổi tên, quyền và chính sách trùng. Các task **Copy**, **Sync**, **Zip**, **Tar**, **Jar** đều dùng những khái niệm CopySpec; mỗi loại task có hành vi đầu ra riêng.

| API | Mục đích | Cần lưu ý |
| --- | --- | --- |
| **from(...)** | Chọn một hoặc nhiều nguồn | Directory là một hierarchy, không mặc nhiên sao chép tên thư mục gốc |
| **into(...)** | Chọn thư mục đích toàn task hoặc tiền tố ở child spec | Với archive, **into** bên trong archive là đường dẫn *trong archive* |
| **include(...)** | Chỉ lấy những đường dẫn khớp pattern | Pattern thường kiểu Ant glob |
| **exclude(...)** | Loại đường dẫn không mong muốn | Loại trừ thắng điều kiện bao gồm |
| **rename(...)** | Đổi tên file khi copy | Chủ yếu đổi **basename**; không phải cách chung để đổi mọi tầng thư mục |
| **eachFile { ... }** | Xử lý từng entry, xem/sửa path, loại entry, đổi duplicate policy | Cần hiểu đường dẫn đích sau transform |
| **duplicatesStrategy** | Xử lý nhiều nguồn ánh xạ tới cùng đích | Không tự sửa tên file hoặc tránh collision logic |
| **filePermissions { ... }** | Quyền của file đích | Tách biệt với quyền directory |
| **dirPermissions { ... }** | Quyền của directory đích | Directory cần quyền traverse/execute khi dùng Unix |
| **includeEmptyDirs** | Có giữ directory rỗng trong phép copy hay không | Thư mục rỗng có thể bị bỏ khi đặt **false** |

Đặc điểm quan trọng: **CopySpec có thể lồng nhau**. Child spec thừa hưởng nhiều lựa chọn từ parent; bạn có thể đặt filter/quyền riêng cho chỉ một nhóm nguồn, thay vì áp một chính sách cho mọi tài nguyên.

### 2.1. Ví dụ về scope của filter

~~~groovy
tasks.register('copyDocsOnly', Copy) {
    into(layout.buildDirectory.dir('docs-only'))

    from('src/dist/common') {
        include('docs/**')
    }

    from('src/dist/addons') {
        into('addons')
    }
}
~~~

**include('docs/**')** chỉ áp dụng cho nguồn **common** vì nó nằm trong child spec của **from('src/dist/common')**. Nguồn **addons** không bị giới hạn bởi filter này. Nếu đặt **include('docs/**')** ở root task, nó có thể lọc cả những nguồn khác và vô tình loại **addons/NOTICE.txt**.

**Quy tắc lọc:** nếu không khai báo include/exclude, thường nhận toàn bộ nội dung nguồn. Khi có include, chỉ những đường dẫn phù hợp được đưa vào; exclude có thể loại bỏ dù đường dẫn cũng khớp include. Khi cần file nằm sâu trong cây, dùng glob kiểu **'**/*.txt'**, không chỉ **'*.txt'** ở cấp thư mục hiện tại.

## 3. DuplicatesStrategy: định nghĩa chính xác từng lựa chọn

Khi hai file nguồn được ánh xạ đến cùng **đường dẫn tương đối đích**, Gradle dùng **org.gradle.api.file.DuplicatesStrategy** để quyết định xử lý. Các giá trị:

| Strategy | Khi gặp entry thứ hai có cùng đích | Thường dùng khi |
| --- | --- | --- |
| **FAIL** | Ném **DuplicateFileCopyingException** và làm task thất bại | Cần kiểm soát chặt, tránh mất dữ liệu không chủ ý |
| **EXCLUDE** | Bỏ entry tới sau, giữ entry đã tạo đầu tiên | Chủ đích ưu tiên nguồn đầu; nên chứng minh thứ tự |
| **INCLUDE** | Cho phép cả hai; đích là filesystem không hỗ trợ hai file cùng path thì entry tới sau có thể ghi đè | Trường hợp thật sự chấp nhận trùng |
| **WARN** | Giống INCLUDE nhưng phát cảnh báo | Điều tra collision mà vẫn cho phép copy |
| **INHERIT** | Dùng strategy của parent CopySpec | Khi muốn child tuân theo chính sách chung |

**Giá trị mặc định của CopySpec là INHERIT**. Nếu không có strategy cụ thể được kế thừa và gặp tệp trùng, Gradle hiện đại báo lỗi. Vì vậy, với task đóng gói quan trọng, nên **khai báo FAIL tường minh**; đừng dựa vào giả định từ một bản Gradle cũ hoặc plugin khác.

### 3.1. Minh họa một collision

Hai nguồn trong fixture:

~~~text
src/dist/common/conf/app.properties
src/dist/overrides/conf/app.properties
~~~

Nếu dùng:

~~~groovy
import org.gradle.api.file.DuplicatesStrategy

tasks.register('checkDuplicates', Copy) {
    from('src/dist/common')
    from('src/dist/overrides')
    into(layout.buildDirectory.dir('checks/duplicates'))
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

cả hai file đều sẽ cố tạo **conf/app.properties**. Khi hai file nguồn thực sự tồn tại và được chọn, task **checkDuplicates** sẽ thất bại vì conflict; đây là hành vi **mong đợi của bài kiểm tra**, không phải lỗi cú pháp.

**Không đồng nhất collision giữa hai nguồn của một operation với “một file đã tồn tại trong đích từ lần build trước”**. Duplicate strategy chủ yếu giải quyết các entry cạnh tranh trong copy operation, không phải cơ chế bảo vệ mọi file đã có trên ổ đĩa. Để tránh ghi đè thủ công vào vùng output, dùng thư mục do build sở hữu và quy trình rõ ràng.

### 3.2. EXCLUDE: entry đầu tiên thắng, nhưng thứ tự phải đáng tin

~~~groovy
tasks.register('firstWins', Copy) {
    from('src/dist/common')
    from('src/dist/overrides')
    into(layout.buildDirectory.dir('checks/first-wins'))
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
}
~~~

Với hai nguồn trong thứ tự liệt kê cố định của ví dụ, bản **conf/app.properties** từ **common** được chọn trước, bản từ **overrides** sẽ bị bỏ. Vì thế nội dung đích dự kiến là **mode=base**.

Nhưng **EXCLUDE không diễn đạt một chính sách merge có kiểm tra ưu tiên theo metadata**. Nếu danh sách nguồn sinh động từ FileTree, plugin hoặc runtime classpath mà thứ tự không được bạn kiểm soát, việc “bản nào tới trước” có thể không phù hợp kỳ vọng nghiệp vụ. Khi ưu tiên bản override là quan trọng, nên **tách đường dẫn**, **loại nguồn xung đột có chủ đích** hoặc viết quy trình merge được kiểm thử, thay vì trông chờ vào trật tự không rõ ràng.

### 3.3. INCLUDE và WARN: cảnh giác khi đóng gói ZIP/JAR

~~~groovy
tasks.register('warnOnDuplicates', Copy) {
    from('src/dist/common')
    from('src/dist/overrides')
    into(layout.buildDirectory.dir('checks/warn'))
    duplicatesStrategy = DuplicatesStrategy.WARN
}
~~~

**WARN** hành xử như **INCLUDE**, nhưng log cảnh báo. Trên filesystem thường không chứa được hai file cùng path, entry tới sau có thể **ghi đè** file trước. Tuy vậy trong **ZIP/JAR** có thể tồn tại nhiều archive entry **cùng tên**; công cụ giải nén hoặc đọc JAR có thể xử lý các entry đó theo cách khác nhau. Vì thế không dùng **INCLUDE/WARN** để “giải quyết” trùng các resource cấu hình quan trọng.

Ví dụ rủi ro: hai dependency chứa file **META-INF/services/com.example.Service**. Nếu gom JAR theo cách thô, **EXCLUDE** có thể bỏ provider cần thiết, **INCLUDE** có thể tạo entry trùng và cách đọc không nhất quán. Khi cần **merge service descriptors**, hãy dùng quy trình xử lý chuyên biệt (chẳng hạn công cụ hỗ trợ merge resource), kiểm chứng nội dung đầu ra; đổi duplicate policy không thực hiện phép hợp nhất văn bản.

### 3.4. Đặt strategy ở mức hẹp

Có thể áp dụng strategy cho toàn task:

~~~groovy
duplicatesStrategy = DuplicatesStrategy.FAIL
~~~

Hoặc áp dụng trên child spec:

~~~groovy
from('src/dist/overrides') {
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
}
~~~

API **eachFile** / **filesMatching** cũng có thể điều chỉnh strategy theo từng entry. Tuy nhiên, giải pháp an toàn và dễ đọc nhất thường là **FAIL ở mức root**, sau đó giải quyết nguyên nhân bằng sửa cấu trúc, lọc hay rename có mục đích. Tránh nhiều override chồng nhau khiến khó hiểu file nào được giữ.

## 4. Lý do phổ biến dẫn đến tệp trùng

### 4.1. Hai from trỏ tới cây có đường dẫn tương đối giống nhau

~~~groovy
from('src/dist/common')
from('src/dist/overrides')
~~~

Cả hai có **conf/app.properties** nên trùng. Có thể tránh bằng cách đặt prefix cho một nguồn:

~~~groovy
from('src/dist/common')
from('src/dist/overrides') {
    into('overrides')
}
~~~

Kết quả là hai đường dẫn khác nhau: **conf/app.properties** và **overrides/conf/app.properties**.

### 4.2. Đổi tên tạo collision mới

Giả sử cùng một thư mục có **config-draft.txt** và **config.txt**. Nếu dùng:

~~~groovy
rename { name -> name.replace('-draft', '') }
~~~

thì cả hai có thể trở thành **config.txt**. Duplicate strategy chỉ phát hiện ở **đường dẫn sau rename**. Để sửa, chọn tên khác không xung đột, lọc một trong hai file, hoặc nêu rõ chính sách ưu tiên.

**rename** trong CopySpec là cách đổi **tên entry**, không phải công cụ đảm bảo bảo toàn mọi quan hệ thư mục. Nếu muốn đổi toàn bộ path, xem **eachFile** hoặc bố trí child specs.

### 4.3. Flatten cấu trúc khiến các tên file đụng nhau

Giả sử:

~~~text
src/dist/common/docs/readme.txt
src/dist/common/conf/readme.txt
~~~

Nếu xóa tầng thư mục và chỉ giữ basename, cả hai trở thành **readme.txt** ở cùng thư mục đích.

Ví dụ **có chủ đích tạo collision** để hiểu cơ chế:

~~~groovy
tasks.register('flattenText', Copy) {
    from('src/dist/common')
    include('**/*.txt')
    into(layout.buildDirectory.dir('flattened'))
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL

    eachFile { details ->
        details.path = details.name
    }
}
~~~

**FileCopyDetails.path** là đường dẫn đích tương đối, dùng dấu **/** làm separator trên mọi nền tảng. **details.path = details.name** loại toàn bộ thư mục cha; code trên **chỉ nên dùng nếu chủ đích flatten**, đã kiểm tra không có basename trùng. Nếu không có hai tên trùng, task chạy và đặt các TXT trực tiếp trong **build/flattened**. Nếu có collision, FAIL giúp phát hiện thay vì âm thầm ghi đè.

### 4.4. Chọn trùng file vì include/fileTree/zipTree

Các nguyên nhân khác: cùng file nằm trong hai **from(...)**; dùng **zipTree(...)** để gom nhiều archive có cùng entry; dùng **from(sourceSets.main.output)** rồi lại copy thủ công resources tương tự; hoặc lặp nguồn trong plugin/cấu hình dùng chung.

Tập trung vào **cây đường dẫn sau tất cả CopySpec**, chứ không chỉ tên tệp trước khi copy. Khi báo lỗi collision, vẽ hai đường dẫn nguồn và **một đường dẫn đích**, rồi sửa ánh xạ hoặc dữ liệu.

## 5. Bảo toàn cấu trúc thư mục: from, into, include và empty directories

### 5.1. Giữ cây tương đối mặc định

~~~groovy
tasks.register('copyTree', Copy) {
    from('src/dist/common')
    into(layout.buildDirectory.dir('tree'))
}
~~~

Đây là cách đơn giản nhất nếu muốn **giữ các thư mục con** bên trong nguồn. File **docs/manual.txt** vẫn là **build/tree/docs/manual.txt**. Folder gốc tên **common** không tự xuất hiện.

### 5.2. Giữ thêm một tầng thư mục có tên

~~~groovy
tasks.register('copyParentFolder', Copy) {
    from('src/dist') {
        include('common/**')
    }
    into(layout.buildDirectory.dir('tree-with-parent'))
}
~~~

Kết quả có **build/tree-with-parent/common/docs/manual.txt**. Nguyên nhân là root **from** bây giờ là **src/dist**, nên **common/** nằm trong đường dẫn tương đối được bảo toàn.

Một cách khác là **from('src/dist/common') { into('common') }**, tương tự mục 1. Chọn cách phản ánh rõ nguồn nào và cấu trúc đích nào bạn thực sự muốn.

### 5.3. Đặt tài nguyên theo layout phát hành

~~~groovy
tasks.register('layoutRelease', Copy) {
    into(layout.buildDirectory.dir('layout-release'))

    from('src/dist/common') {
        include('docs/**')
        into('share')
    }

    from('src/dist/addons') {
        into('notices')
    }
}
~~~

File **docs/manual.txt** thành **build/layout-release/share/docs/manual.txt**; file **NOTICE.txt** thành **build/layout-release/notices/NOTICE.txt**.

Trong thư mục **share**, vẫn có tầng **docs** vì child **into('share')** chỉ **thêm prefix**; nó không tự loại tầng thư mục đã có. Nếu muốn kết quả là **share/manual.txt**, hãy dùng **from('src/dist/common/docs') { into('share') }**.

### 5.4. Thư mục rỗng và includeEmptyDirs

CopySpec có property **includeEmptyDirs** (mặc định **true**) để quyết định có đưa các thư mục rỗng vào đích hay không:

~~~groovy
tasks.register('copyWithoutEmptyDirs', Copy) {
    from('src/dist/common')
    into(layout.buildDirectory.dir('no-empty-dirs'))
    includeEmptyDirs = false
}
~~~

Đừng mặc định thao tác lọc file sẽ luôn giữ lại một thư mục chỉ vì nó tồn tại trong nguồn. Nếu ứng dụng thực sự cần thư mục rỗng (ví dụ thư mục logs khi cài đặt), phải biểu đạt và kiểm chứng yêu cầu đó. Với ZIP/TAR, kiểm tra archive entries để xác định các thư mục mong muốn có được bao gồm.

### 5.5. Phân biệt FileTree và FileCollection

**FileTree** là tập file có **cấu trúc tương đối**, hữu ích khi copy cả cây. **FileCollection** có thể là danh sách file **không mang cùng gốc thư mục rõ ràng**; nếu đưa nhiều file riêng lẻ vào một CopySpec, cách bảo toàn đường dẫn có thể khác ý định.

Để bảo toàn layout **src/main/resources/**, thường dùng:

~~~groovy
from('src/main/resources')
~~~

thay vì tự duyệt từng file rồi **from(files(...))** không lưu quan hệ thư mục. Khi xây dựng một archive từ các nguồn khác nhau, nên áp dụng **into** có chủ đích cho mỗi nguồn.

### 5.6. Pattern không đảm bảo mọi đường dẫn có cùng chữ hoa/chữ thường

**caseSensitive** của CopySpec điều khiển cách khớp include/exclude (mặc định true), nhưng filesystem Windows/macOS/Linux có thể khác về **case sensitivity** và hành vi đường dẫn. Hai file **Readme.txt** và **README.txt** có thể hợp lệ trên một filesystem nhưng collision trên hệ khác. Tránh dựa vào duy nhất sự khác biệt hoa/thường để phân biệt artifact cần portable.

## 6. Quyền truy cập: filePermissions, dirPermissions và Unix bits

**Quyền file** và **quyền directory** khác nhau:

- File thường cần **read** để đọc, **write** để chỉnh, **execute** để chạy như chương trình/script theo cơ chế hệ điều hành.
- Directory cần **execute/search** để đi qua và truy cập entry bên trong, ngoài quyền read/list và write/create thích hợp.
- Quyền được chia thành **user/owner**, **group**, **other** theo mô hình Unix; không phải cơ chế đầy đủ của Windows ACL.

Các mode thông dụng:

| Mode | Chuỗi quyền | Ý nghĩa thường dùng |
| --- | --- | --- |
| **0644** | **rw-r--r--** | File dữ liệu: owner đọc/ghi, group/other đọc |
| **0600** | **rw-------** | File riêng tư: chỉ owner đọc/ghi, không thay thế bảo vệ secret toàn diện |
| **0755** | **rwxr-xr-x** | Thư mục thông thường hoặc executable script |
| **0750** | **rwxr-x---** | Thư mục cho owner và group |
| **0700** | **rwx------** | Thư mục riêng của owner |
| **0777** | **rwxrwxrwx** | Mở quyền cho mọi nhóm; thường không an toàn, tránh đặt bừa |

### 6.1. Cấu hình quyền file và thư mục theo CopySpec

Ví dụ Gradle Groovy DSL:

~~~groovy
tasks.register('copyWithModes', Copy) {
    from('src/dist/common')
    into(layout.buildDirectory.dir('with-modes'))

    filePermissions {
        unix('0644')
    }

    dirPermissions {
        unix('0755')
    }
}
~~~

- **filePermissions** đặt mode cho **file đích**.
- **dirPermissions** đặt mode cho **directory đích**.
- **unix('0644')** và **unix('0755')** nhận chuỗi mã quyền, không phải phép đổi quyền trực tiếp trên file nguồn.
- Mọi file nằm trong scope CopySpec trên mặc định được đặt **0644**, kể cả **bin/start.sh**; nếu muốn script chạy trực tiếp trên Unix, cần policy riêng **0755** cho script.
- Gradle tạo destination cần thiết khi Copy task thực thi, nhưng việc áp quyền cuối cùng phụ thuộc hệ điều hành và copy implementation.

Nếu **không đặt quyền tường minh** trong một **Copy/Sync** thông thường, Gradle cố gắng bảo toàn permissions nguồn theo khả năng của copy implementation. Đối với **archive tasks**, quyền mặc định có chính sách riêng phục vụ reproducibility; xem mục 9.

### 6.2. Phân quyền khác nhau cho nhóm file và scripts

Thay vì cài **0755 cho toàn bộ file**, hãy tách nguồn theo child spec:

~~~groovy
import org.gradle.api.file.DuplicatesStrategy

tasks.register('stageRelease', Copy) {
    into(layout.buildDirectory.dir('staging/release'))
    duplicatesStrategy = DuplicatesStrategy.FAIL
    includeEmptyDirs = false

    filePermissions {
        unix('0644')
    }
    dirPermissions {
        unix('0755')
    }

    // Data, docs, cấu hình: không cấp execute.
    from('src/dist/common') {
        exclude('bin/**')
    }

    // Chỉ scripts: cấp execute.
    from('src/dist/common/bin') {
        into('bin')
        filePermissions {
            unix('0755')
        }
    }

    // Giữ addon trong thư mục riêng, tránh tên trùng.
    from('src/dist/addons') {
        into('addons')
    }
}
~~~

Đây là **task thực hành chính**. Nguồn tồn tại đúng như fixture mục 1, không có collision và destination nằm trong **build/**.

Cây đích dự kiến:

~~~text
build/staging/release/
├── README.txt
├── conf/app.properties
├── docs/manual.txt
├── bin/start.sh
└── addons/NOTICE.txt
~~~

Về ý nghĩa permissions trên filesystem hỗ trợ Unix mode:

- **README.txt**, **conf/app.properties**, **docs/manual.txt** và **addons/NOTICE.txt**: **0644**.
- **bin/start.sh**: **0755** nhờ child CopySpec dành riêng.
- Directory đầu ra theo chính sách **0755** khi triển khai áp dụng quyền.

**Tại sao không chỉ chmod mọi file 0755?** Khi mọi file đều executable, quyền không phản ánh chức năng, làm chính sách bảo mật kém chặt chẽ và gây khó khăn cho kiểm tra artifact.

### 6.3. Quyền trên một file cụ thể qua eachFile

Gradle hỗ trợ:

~~~groovy
tasks.register('copyScriptWithPerFileMode', Copy) {
    from('src/dist/common')
    into(layout.buildDirectory.dir('per-file-mode'))

    eachFile {
        if (name == 'start.sh') {
            permissions {
                user.execute = true
            }
        }
    }
}
~~~

**Đây là ví dụ về API**, không phải lựa chọn mặc định cho task muốn up-to-date. Theo tài liệu Gradle, **thiết lập permissions tường minh trên từng file bằng cách này không hỗ trợ UP-TO-DATE checks**: task dùng cấu hình như vậy có thể phải chạy mọi lần. Khi có thể, nên tách nhóm nguồn bằng **child CopySpec.filePermissions**, như task **stageRelease**, để chính sách rõ ràng và tránh ảnh hưởng đó.

**Lưu ý hệ điều hành:** Windows NTFS dùng ACL và cơ chế thực thi khác Unix. Mode Unix trong ZIP/TAR và mode trên filesystem host không phải cùng một thứ. Kiểm thử trên nền tảng deploy thật nếu ứng dụng phụ thuộc bit executable hoặc owner/group; không tuyên bố rằng một bản copy sẽ tự bảo toàn đầy đủ POSIX owner, ACL, symlink và mọi metadata trên mọi OS.

## 7. Cách chạy và kiểm chứng task stageRelease

Đảm bảo project có Gradle Wrapper hợp lệ và các file fixture. Trên Linux/macOS:

~~~bash
./gradlew stageRelease
find build/staging/release -type f -print
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat stageRelease
Get-ChildItem .\build\staging\release -Recurse -File |
    ForEach-Object { $_.FullName }
~~~

Không chép lại “log chính xác” vì Gradle có thể khác phiên bản/cấu hình; hãy **đối chiếu cây file** với mục 6.2.

Trên Linux có thể xem mode nếu filesystem hỗ trợ:

~~~bash
stat -c '%a %n' build/staging/release/README.txt
stat -c '%a %n' build/staging/release/bin/start.sh
stat -c '%a %n' build/staging/release/conf
~~~

Khi quyền được áp dụng như ví dụ, phần mode dự kiến là **644**, **755**, **755** tương ứng (không bắt buộc có số 0 ở đầu cách hiển thị). Trên macOS BSD **stat** dùng cú pháp khác; ví dụ:

~~~bash
stat -f '%Lp %N' build/staging/release/bin/start.sh
~~~

Trên Windows, **Get-Acl** có thể kiểm tra access control tại filesystem, nhưng **không tương đương trực tiếp** với mode Unix trong một tarball. Để kiểm tra artifact sẽ triển khai sang Linux, xem quyền trong archive và kiểm chứng sau giải nén trên Linux.

**Kiểm tra nội dung file:** mở **build/staging/release/conf/app.properties** và xác nhận **mode=base** (không có bản overrides vì task không thêm nguồn này ở cùng đích). Với policy **FAIL**, nếu sau này một nguồn mới tạo cùng đường dẫn, build sẽ báo vấn đề thay vì im lặng ghi đè.

## 8. Copy khác Sync: nguy cơ xóa file đích

| Task | Tác dụng chính | Rủi ro đáng chú ý |
| --- | --- | --- |
| **Copy** | Sao chép những file được chọn vào destination | Có thể ghi đè file đích; thường không xóa những file không còn thuộc nguồn |
| **Sync** | Làm destination khớp với tập nguồn đã chọn | Có thể **xóa nội dung đích không được copy**, kể cả file do người dùng tạo trong đó |
| **Zip/Tar** | Đóng gói entry vào một archive | Có thể tạo entry trùng, thay mode/timestamp, hoặc thay đổi cấu trúc nếu into sai |

Ví dụ **chỉ dành cho thư mục build do Gradle quản lý**:

~~~groovy
tasks.register('syncRelease', Sync) {
    from('src/dist/common')
    into(layout.buildDirectory.dir('synced-release'))
    duplicatesStrategy = DuplicatesStrategy.FAIL
    includeEmptyDirs = false
}
~~~

Lần đầu task đưa nội dung nguồn vào **build/synced-release**. Nếu sau đó bạn xóa một file nguồn và **syncRelease** thực sự thực thi, tệp tương ứng ở destination có thể bị xóa để destination khớp nguồn. **Đây chính là chức năng Sync, không phải lỗi.**

### 8.1. Vì sao không Sync vào thư mục dữ liệu người dùng?

Một cấu hình không an toàn:

~~~groovy
// KHÔNG DÙNG cho thư mục chứa dữ liệu người dùng hay source cần giữ.
tasks.register('unsafeSync', Sync) {
    from('src/dist/common')
    into('src')   // Nguy hiểm: có thể xóa nội dung ngoài tập source được chọn
}
~~~

Không chạy ví dụ **unsafeSync**. Nó chỉ minh họa phạm vi xóa sai. **Sync không biết thư mục nào “quan trọng với người dùng”**; muốn dùng Sync, chỉ định một destination cô lập, do task sở hữu, và tuyệt đối không trỏ tới project root, src, home directory hay thư mục deploy có dữ liệu sống.

### 8.2. preserve chỉ dành cho ngoại lệ được kiểm soát

Có thể cấu hình **preserve { ... }** để không xóa các tệp đích phù hợp khi Sync dọn những tệp không thuộc nguồn:

~~~groovy
tasks.register('syncWithPreserve', Sync) {
    from('src/dist/common')
    into(layout.buildDirectory.dir('synced-preserve'))

    preserve {
        include('keep-local.txt')
    }
}
~~~

Nếu đã tồn tại **build/synced-preserve/keep-local.txt**, policy preserve cho phép giữ file này trong quá trình Sync dọn destination. Tuy nhiên, **preserve không phải cơ chế backup**: nó không bảo vệ mọi file chưa liệt kê và không giải quyết tình huống file nguồn có cùng path với file preserved. Chỉ dùng khi hiểu chính xác phạm vi.

### 8.3. Trường hợp source rỗng

Gradle phiên bản mới có cơ chế đặc biệt cho Sync khi source không chứa file hoặc directory: task có thể bị skip, hoặc destination được xử lý theo ownership của build. Một số bản Gradle cung cấp **skipWhenSourceIsEmpty** (API incubating) để điều khiển điều này.

**Không dựa vào giả định “source rỗng thì Sync luôn xóa sạch” hoặc “luôn giữ nguyên”**. Kiểm tra tài liệu đúng phiên bản và thử trong **build/** trước khi triển khai. Dù có cấu hình skip hay preserve, chọn destination không chứa dữ liệu quan trọng vẫn là yêu cầu an toàn cốt lõi.

## 9. Trong ZIP/TAR: đường dẫn bên trong, duplicate entry và quyền

Archive task như **Zip**, **Tar** và **Jar** cũng dùng CopySpec. Điểm khác là destination là **một file archive**, còn **into('release')** là thư mục **bên trong archive**, không phải đường dẫn máy.

### 9.1. Ví dụ tạo ZIP từ staging, có chính sách tường minh

Sau khi định nghĩa task **stageRelease** ở mục 6.2, thêm:

~~~groovy
tasks.register('zipRelease', Zip) {
    dependsOn(tasks.named('stageRelease'))

    archiveFileName = 'release.zip'
    destinationDirectory = layout.buildDirectory.dir('packages')
    duplicatesStrategy = DuplicatesStrategy.FAIL
    includeEmptyDirs = false

    filePermissions {
        unix('0644')
    }
    dirPermissions {
        unix('0755')
    }

    // Nhóm data/doc thường ở mode 0644.
    from(layout.buildDirectory.dir('staging/release')) {
        exclude('bin/**')
        into('release')
    }

    // Nhóm script phải có execute bit trong archive.
    from(layout.buildDirectory.dir('staging/release/bin')) {
        into('release/bin')
        filePermissions {
            unix('0755')
        }
    }
}
~~~

Điều đáng học:

- **dependsOn** diễn đạt task ZIP cần staging có sẵn. Trong ví dụ này dependency được khai báo tường minh.
- **archiveFileName** đặt tên **release.zip**; **destinationDirectory** là folder của file ZIP trên ổ đĩa.
- Hai lệnh **from** bên trong ZIP định nghĩa **entry paths**. File **docs/manual.txt** thành **release/docs/manual.txt**.
- File **start.sh** được đưa vào **release/bin/start.sh**, không bị đưa lần hai vì nhánh đầu đã **exclude('bin/**')**.
- Mode data được cấu hình **0644**, script được cấu hình **0755**, directory **0755** bên trong archive.
- **duplicatesStrategy = FAIL** giữ nguyên chính sách cấm trùng đường dẫn archive entry.

Chạy:

~~~bash
./gradlew zipRelease
~~~

Đường dẫn file đích: **build/packages/release.zip**.

Bạn có thể liệt kê những entry bằng công cụ JDK:

~~~bash
jar tf build/packages/release.zip
~~~

Trên Windows PowerShell:

~~~powershell
jar tf .\build\packages\release.zip
~~~

Trong danh sách, cần tìm các đường dẫn:

~~~text
release/README.txt
release/conf/app.properties
release/docs/manual.txt
release/bin/start.sh
release/addons/NOTICE.txt
~~~

Archive có thể liệt kê thêm directory entries; thứ tự hiển thị không nên xem là chứng cứ duy nhất về cấu trúc. Dùng **unzip -l** để xem tên và dung lượng, hoặc **zipinfo -v** (nếu có) để kiểm tra quyền trong ZIP. **jar tf** chủ yếu kiểm tra entry names, không phải toàn bộ metadata quyền.

### 9.2. Vì sao không dùng INCLUDE với ZIP nếu chưa biết chính xác?

Một ZIP có thể chứa hai entry đều tên **release/conf/app.properties**. Khi gặp duplicates, **INCLUDE** cho phép ghi cả hai, còn **WARN** vẫn cho phép và thêm cảnh báo. Công cụ đọc ZIP có thể chọn một trong các entry hoặc báo lỗi. Vì thế:

- Chọn **FAIL** với artifacts cần độc lập và tái lập.
- Nếu muốn ưu tiên một file: loại file còn lại bằng include/exclude, thay đổi child **into**, hoặc thực hiện merge rõ ràng.
- Nếu muốn hợp nhất nội dung của hai file: cần công cụ/logic merge riêng, không chỉ đặt **INCLUDE**.

Cùng nguyên tắc này áp dụng cho **Jar** và **Tar** khi tạo archive chứa resource từ nhiều nguồn.

### 9.3. Quyền và archive reproducibility từ Gradle 9

Theo tài liệu Gradle hiện hành, **từ Gradle 9**, các **AbstractArchiveTask** (gồm ZIP/JAR/TAR) tạo archive có cấu hình tái lập theo mặc định:

- Thứ tự entry được sắp xếp có tính quyết định.
- Timestamp được cố định theo định dạng archive.
- Mode directory mặc định là **0755**.
- Mode file mặc định là **0644**.

Điều này **khác Copy thông thường**, vốn không đặt permission tường minh thì thường cố bảo toàn permission nguồn. Hệ quả: nếu một shell script có executable bit ở filesystem nhưng được đóng gói vào ZIP/JAR/TAR Gradle 9+ với mode file mặc định **0644**, script có thể **mất executable bit trong archive**, trừ khi cấu hình mode cụ thể hoặc chọn bảo toàn filesystem permissions.

Tùy nhu cầu, bạn có thể cấu hình rõ:

~~~groovy
tasks.register('zipScripts', Zip) {
    archiveFileName = 'scripts.zip'
    destinationDirectory = layout.buildDirectory.dir('packages')
    from('src/dist/common/bin')
    duplicatesStrategy = DuplicatesStrategy.FAIL

    filePermissions {
        unix('0755')
    }
    dirPermissions {
        unix('0755')
    }
}
~~~

Đây là archive **chỉ chứa scripts** theo fixture, vì vậy mode file **0755** là hợp lý.

### 9.4. Khi thực sự muốn bảo toàn permissions/timestamps của filesystem

Gradle 9+ có API **useFileSystemPermissions()** đối với archive task để sử dụng mode từ filesystem thay cho mode cố định. Ví dụ **chỉ khi chính sách phát hành yêu cầu**:

~~~groovy
tasks.register('zipWithSourcePermissions', Zip) {
    archiveFileName = 'source-permissions.zip'
    destinationDirectory = layout.buildDirectory.dir('packages')
    from('src/dist/common')
    duplicatesStrategy = DuplicatesStrategy.FAIL
    useFileSystemPermissions()
}
~~~

Cách này có thể làm archive khác nhau theo OS/checkout vì quyền file nguồn không đồng nhất. Nếu cần bảo toàn timestamp, **preserveFileTimestamps = true** cũng làm giảm khả năng tái lập nếu timestamp filesystem thay đổi; nếu cần bảo toàn thứ tự filesystem, **reproducibleFileOrder = false** có rủi ro tương tự. Không bật cả ba chỉ vì tên nghe giống “preserve structure”: chúng liên quan **metadata và thứ tự**, không phải cây thư mục do from/into quyết định.

**Bảo toàn cấu trúc** và **bảo toàn metadata** là hai yêu cầu độc lập. Có thể cần giữ cây thư mục nhưng lại muốn timestamp và permissions được chuẩn hóa để dễ tái lập.

### 9.5. TAR và ZIP khác nhau thế nào về kiểm tra?

Task **Tar** có kiểu archive và option **compression** thích hợp; task **Zip** tạo file ZIP. Với TAR, công cụ **tar -tf** liệt kê entry; **tar -tvf** thường hiển thị thêm mode và metadata trong archive. Với ZIP, **jar tf** hoặc **unzip -l** hiển thị entry nhưng mode cần công cụ hỗ trợ như **zipinfo -v**.

Dù dùng archive gì, kiểm tra **sau đóng gói** chứ không chỉ sau staging: có thể quyền file chính xác ở **build/staging/** nhưng bị thay đổi bởi chính sách reproducible archive.

## 10. Chọn chính sách theo từng tình huống

### Tình huống A — Hai folder khác nhau đều chứa config/app.properties

**Mục tiêu:** đưa cả hai vào artifact để người dùng xem được.

**Cách tốt:** đặt prefix tường minh:

~~~groovy
tasks.register('copyBothConfigs', Copy) {
    into(layout.buildDirectory.dir('both-configs'))
    duplicatesStrategy = DuplicatesStrategy.FAIL

    from('src/dist/common') {
        into('defaults')
    }
    from('src/dist/overrides') {
        into('overrides')
    }
}
~~~

Cây đích có **defaults/conf/app.properties** và **overrides/conf/app.properties**. Hai bản không đụng nhau và rõ ý nghĩa nghiệp vụ.

### Tình huống B — Bắt buộc chỉ có một config/app.properties

**Mục tiêu:** một source là nguồn chân lý.

**Cách tốt:** xác định nguồn chính ở build logic, chỉ copy file từ nguồn đã chọn. Ví dụ chỉ dùng bản override:

~~~groovy
tasks.register('copySelectedConfig', Copy) {
    from('src/dist/overrides') {
        include('conf/app.properties')
    }
    into(layout.buildDirectory.dir('selected-config'))
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

Không cần **EXCLUDE** để ưu tiên vì chỉ có một nguồn. Nếu muốn merge hai nội dung, hãy thiết kế task merge thật sự với input/output rõ ràng và quy tắc xung đột có kiểm thử.

### Tình huống C — Script cần chạy trên Linux, file JSON/TXT không cần execute

**Mục tiêu:** mode chỉ khác ở nhóm script.

**Cách tốt:** dùng **filePermissions** ở child CopySpec dành cho scripts, mode mặc định **0644** cho data và **dirPermissions 0755** cho directories. Khi đóng gói ZIP/TAR, **kiểm tra mode bên trong archive**, không chỉ mode staging.

### Tình huống D — Muốn giữ folder docs nhưng không muốn folder sourceRoot

**Mục tiêu:** **out/docs/guide.txt** từ **src/sourceRoot/docs/guide.txt**.

**Cách tốt:** **from('src/sourceRoot')**, **into('out')**; tên **sourceRoot** không tự xuất hiện. Nếu muốn **out/sourceRoot/docs/guide.txt**, dùng child **into('sourceRoot')** hoặc thay root from thành cấp cha phù hợp.

### Tình huống E — Muốn artifact sạch, bỏ file đã bị xóa khỏi nguồn

**Mục tiêu:** output luôn khớp nguồn được quản lý.

**Cách tốt:** **Sync** vào một thư mục **riêng trong build/**. Không Sync vào thư mục nhiều bên cùng ghi hoặc có dữ liệu người dùng. Nếu cần ngoại lệ, dùng **preserve** thật hạn chế và kiểm thử behavior khi nguồn trống.

### Tình huống F — Giải nén ZIP từ bên thứ ba

Có thể dùng **zipTree('path/to/archive.zip')** trong **from(...)** của Copy task:

~~~groovy
tasks.register('extractArchive', Copy) {
    from(zipTree('vendor/demo.zip'))
    into(layout.buildDirectory.dir('extracted'))
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

Đây là **đoạn cấu hình minh họa**, chỉ chạy khi **vendor/demo.zip** là archive hợp lệ mà bạn tin cậy. Không chỉ cần xem duplicates: khi xử lý archive ngoài, phải quan tâm tới **đường dẫn bất thường**, nội dung không đáng tin cậy, lượng dữ liệu được giải nén và quyền đầu ra. Đừng mặc định archive bên ngoài luôn có cấu trúc an toàn.

## 11. Checklist kiểm chứng sau khi Copy/Sync/Zip

| Câu hỏi | Cách kiểm chứng |
| --- | --- |
| Đúng file nào được copy? | Liệt kê cây **build/staging** và so với fixture/input |
| Thư mục nguồn có bị thêm sai một tầng? | Kiểm tra **README.txt** nằm ở root hay trong **common/** |
| File con có giữ đường dẫn? | Kiểm tra **conf/**, **docs/**, **bin/** |
| Hai nguồn có collision không? | Dùng **DuplicatesStrategy.FAIL**, chạy trên fixture có tệp trùng |
| Rename có tạo collision không? | Kiểm tra những file có cùng basename sau rename |
| Quyền file data đúng chưa? | Linux: **stat -c '%a %n'**; xem loại file |
| Quyền executable script đúng chưa? | Kiểm tra **bin/start.sh** trên host deploy hoặc trong archive |
| Directory có quyền traverse không? | Kiểm tra mode **0755** hoặc mode mong muốn |
| Archive có entry trùng không? | Liệt kê ZIP/TAR và tìm path lặp |
| ZIP có giữ bit execute không? | Dùng công cụ xem metadata archive; kiểm thử giải nén trên Linux |
| Sync có xóa nhầm file không? | Chỉ thử trong output cô lập, tạo file dư giả lập để quan sát |
| Build có tái lập không? | So sánh archive tạo trên môi trường kiểm soát; tránh timestamp/permission ngẫu nhiên |

**Đừng đánh giá chỉ từ BUILD SUCCESSFUL.** Một task có thể thành công nhưng tạo layout sai, ghi đè config không mong muốn hoặc mất executable bit. Chính sách đúng phải kiểm tra **tên, đường dẫn, nội dung, permissions và khả năng chạy ở môi trường đích**.

## 12. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Hướng sửa |
| --- | --- | --- |
| **Entry ... is a duplicate** | Hai nguồn ánh xạ tới cùng path, không có policy chấp nhận | Dùng FAIL để tìm nguồn, sửa ánh xạ/rename/filter; đừng tắt lỗi mù quáng |
| **EXCLUDE** giữ nhầm file | Source order không diễn đạt đúng ưu tiên nghiệp vụ | Chỉ copy nguồn được chọn hoặc làm merge có kiểm thử |
| ZIP có hai entry cùng tên | **INCLUDE/WARN** cho phép duplicates | Đặt FAIL và sửa dữ liệu/trật tự source |
| Tệp đích bị ghi đè dù không có duplicate exception | File đã tồn tại trước phép Copy, không phải collision giữa source entries | Chọn output do build sở hữu, kiểm tra quy trình publish |
| Bị mất tầng **common** | **from(common)** copy nội dung, không copy tên root | Dùng child **into('common')** hoặc chọn root từ cha |
| Có thêm tầng thư mục ngoài ý muốn | **from** chọn cấp cha khác hoặc child **into** thêm prefix | Vẽ đường dẫn tương đối sau từng CopySpec |
| **docs/** rỗng không xuất hiện | **includeEmptyDirs=false** hoặc filter không giữ thư mục | Kiểm tra requirement về empty dirs và setting |
| Script không thực thi được sau đóng gói | Archive đã chuẩn hóa file mode về **0644** | Đặt mode **0755** cho scripts, kiểm tra metadata archive |
| Toàn bộ file đều có execute bit | Đặt **filePermissions 0755** ở root | Chỉ đặt mode 0755 cho nhóm executable |
| Quyền khác giữa Linux và Windows | Filesystem/ACL/Unix mode không tương đương | Test trên OS đích và xem archive metadata |
| Task thay đổi trạng thái UP-TO-DATE sau eachFile.permissions | Per-file permission override ảnh hưởng up-to-date check | Ưu tiên phân nhóm child CopySpec và quyền tường minh theo nhóm |
| Sync xóa file quan trọng | Destination chứa dữ liệu không do Sync sở hữu | Đổi sang thư mục build cô lập, xem preserve/Copy phù hợp |
| **filePermissions** không tồn tại | Wrapper Gradle quá cũ | Kiểm tra version; dùng API được phiên bản hỗ trợ hoặc nâng cấp có kiểm thử |
| Path khác nhau giữa máy | Dùng absolute path, CWD, hoặc case-sensitive assumptions | Dùng ProjectLayout/Provider, path tương đối và naming portable |
| CI và local tạo ZIP khác byte | Khác timestamp, mode nguồn, thứ tự entries, plugin/runtime hoặc nội dung | Dùng chính sách reproducible phù hợp, so sánh điều kiện đầu vào |
| Copy from output task khác nhưng thiếu thứ tự | Tự đọc đường dẫn do task tạo thay vì nối Provider/task output | Truyền task output Provider vào from, hoặc khai báo dependency rõ |
| ZIP chứa cấu trúc đúng nhưng sai quyền | Chỉ kiểm tra folder staging | Kiểm tra và cấu hình quyền trên chính ArchiveTask |

## 13. Bài tập tự luyện có đáp án

### Bài 1 — Đường dẫn đích

Nguồn là **src/dist/common/docs/manual.txt**. Task:

~~~groovy
tasks.register('practice1', Copy) {
    from('src/dist/common')
    into(layout.buildDirectory.dir('practice1'))
}
~~~

**Hỏi:** file nằm ở đâu?

**Đáp án:** **build/practice1/docs/manual.txt**. Thư mục **common** không tự trở thành tầng trong đích vì là gốc nguồn.

### Bài 2 — Phát hiện collision

Hai nguồn có **conf/app.properties**. Task dùng hai **from** không có child prefix và **duplicatesStrategy = DuplicatesStrategy.FAIL**.

**Đáp án:** khi cả hai file nguồn thực sự được lấy, task thất bại do trùng đường dẫn **conf/app.properties**. Có thể sửa bằng child **into('overrides')** hoặc chỉ chọn một nguồn.

### Bài 3 — INCLUDE vs EXCLUDE trong ZIP

**Hỏi:** Có nên dùng **INCLUDE** để gộp hai entry cùng tên **META-INF/services/service.Name**?

**Đáp án:** không nên coi đó là phép merge. INCLUDE cho phép duplicates trong ZIP, còn cách consumer xử lý là một vấn đề khác. Cần merge nội dung theo quy tắc chuyên biệt và kiểm tra kết quả.

### Bài 4 — Mode file dữ liệu và script

**Hỏi:** Khi data cần 0644, script cần 0755, directory cần 0755, nên đặt permissions ở đâu?

**Đáp án:** **filePermissions { unix('0644') }** và **dirPermissions { unix('0755') }** ở root CopySpec; đặt **filePermissions { unix('0755') }** ở child spec chuyên sao chép scripts, hoặc dùng cơ chế khác có semantics được kiểm thử.

### Bài 5 — Bảo toàn tên folder gốc

**Hỏi:** Muốn **build/out/common/conf/app.properties** từ **src/dist/common/conf/app.properties** thì cấu hình thế nào?

**Đáp án:** **from('src/dist/common') { into('common') }** với root **into(layout.buildDirectory.dir('out'))**, hoặc **from('src/dist') { include('common/**') }**.

### Bài 6 — Tại sao Sync nguy hiểm?

**Hỏi:** Sync một tập file config vào thư mục user home có an toàn không nếu dùng **EXCLUDE** cho duplicates?

**Đáp án:** không. **DuplicatesStrategy** xử lý collision giữa source entries; **Sync** vẫn có thể xóa các file hiện có ở destination mà không thuộc tập copy. Chọn destination riêng thuộc build, hoặc dùng cơ chế copy/deploy khác.

### Bài 7 — Quyền có thay đổi trong ZIP không?

**Hỏi:** Source **start.sh** có mode 0755 trên Linux. Dùng task Zip Gradle 9+ mặc định, không cấu hình mode. Có bảo đảm script giữ mode 0755 trong ZIP không?

**Đáp án:** không. Gradle 9+ dùng mode file mặc định **0644** cho archive tái lập; cần cấu hình **filePermissions** cho script hoặc chọn **useFileSystemPermissions()** có chủ đích, rồi kiểm tra archive thật.

### Bài 8 — Đường dẫn sau rename

Có hai file **config-draft.txt** và **config.txt**, áp dụng **rename { it.replace('-draft','') }** với **FAIL**.

**Đáp án:** hai entry đều có tên **config.txt** nếu cùng thư mục đích, tạo collision; FAIL sẽ giúp phát hiện.

## 14. Checklist thiết kế cho dự án thật

Trước khi thêm task Copy/Sync/Zip/Tar, trả lời:

1. **Source of truth:** tập file nào được phép đi vào artifact? Nguồn nào đến từ task khác?
2. **Destination ownership:** thư mục đích có hoàn toàn do build/task này sở hữu không?
3. **Path mapping:** đã vẽ cây file đích và kiểm tra mọi tầng **from/into/rename** chưa?
4. **Duplicate policy:** có khai báo FAIL rõ ràng hoặc lý do thuyết phục cho policy khác chưa?
5. **Filtering:** include/exclude ở scope root hay child? Có bỏ tệp bắt buộc không?
6. **File permissions:** data cần 0644/0600, scripts cần 0755, directory cần 0755/0750 hay giá trị khác?
7. **Platform:** quyền trong archive và trên OS deploy đã được kiểm tra chưa?
8. **Empty directories:** có cần bảo toàn thư mục rỗng không?
9. **Metadata:** có thực sự phải giữ timestamps và permission nguồn hay nên chọn reproducible output?
10. **Sync risk:** có khả năng xóa nhầm bất kỳ file nào không do task này quản lý?
11. **Verifiability:** có thể liệt kê cây, check nội dung, quyền và phát hiện path lặp trong CI không?
12. **Compatibility:** Gradle Wrapper và plugin đang dùng hỗ trợ các API permissions/reproducibility tương ứng không?

## Tài liệu chính thức

- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): Copy/Sync, tree structure, filtering, permissions và archives.
- [Gradle API — CopySpec](https://docs.gradle.org/current/javadoc/org/gradle/api/file/CopySpec.html): from, into, include/exclude, permissions, duplicatesStrategy.
- [Gradle API — DuplicatesStrategy](https://docs.gradle.org/current/javadoc/org/gradle/api/file/DuplicatesStrategy.html): FAIL, EXCLUDE, INCLUDE, WARN, INHERIT và semantics chính xác.
- [Gradle API — FileCopyDetails](https://docs.gradle.org/current/javadoc/org/gradle/api/file/FileCopyDetails.html): path, name, relativePath, permissions và per-file duplicate policy.
- [Gradle API — ConfigurableFilePermissions](https://docs.gradle.org/current/javadoc/org/gradle/api/file/ConfigurableFilePermissions.html): mode dạng octal/symbolic.
- [Gradle DSL — Copy](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.Copy.html): task copy và thuộc tính.
- [Gradle DSL — Sync](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.Sync.html): đồng bộ và preserve.
- [Gradle DSL — AbstractArchiveTask](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html): ZIP/TAR/JAR, quyền và reproducible archives.

**Tổng kết:** hãy xử lý **tệp trùng bằng chính sách tường minh**, **quyền truy cập theo đúng loại file/directory**, và **cấu trúc đích bằng from/into có kiểm chứng**. Với artifacts quan trọng, lựa chọn mặc định thực dụng thường là **DuplicatesStrategy.FAIL**, input/output nằm trong phạm vi build sở hữu, phân quyền data/script rõ ràng và kiểm tra chính **archive cuối cùng** thay vì chỉ thấy Gradle báo thành công.