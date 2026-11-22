# Phân biệt build chạy lại được với đầu ra tái lập từng byte

Một nhóm có thể chạy lại cùng lệnh build nhiều lần và lần nào cũng nhận được trạng thái thành công. Tuy nhiên, các file đầu ra vẫn có thể khác nhau: một JAR chứa timestamp mới, container image có metadata thay đổi, file ZIP sắp xếp entry theo thứ tự khác hoặc binary nhúng đường dẫn tuyệt đối của máy build. Điều đó có nghĩa build chạy lại được, nhưng đầu ra chưa chắc tái lập được.

Trong CI/CD, sự khác biệt này quan trọng khi nhóm cần xác minh artifact đến từ mã nguồn nào, điều tra sự cố, so sánh build giữa hai runner hoặc chứng minh một gói phát hành có thể được tạo lại độc lập. Bài học này làm rõ hai mức độ đó, chỉ ra các nguồn gây sai khác và trình bày cách chuẩn hóa đầu vào, môi trường, công cụ đóng gói cũng như cách kiểm chứng artifact.

## 1. Hai khái niệm cần phân biệt

### Build chạy lại được

Một build chạy lại được (re-runnable hoặc repeatable theo cách dùng trong bài này) là build có thể được thực thi lại bằng cùng quy trình và hoàn tất thành công. Nhóm có thể chạy lệnh build hôm nay, ngày mai hoặc trên một runner khác mà không phải sửa thủ công từng bước.

Điều này hữu ích cho tự động hóa, nhưng chưa đủ để kết luận hai lần build tạo ra cùng một đầu ra. Lệnh có thể thành công cả hai lần trong khi artifact chứa thời gian tạo, số build, đường dẫn workspace hoặc dependency mới được tải về.

### Build tái lập được từng byte

Build tái lập (reproducible build) yêu cầu hai lần build độc lập, sử dụng cùng đầu vào đã khai báo và quy trình tương đương, tạo ra đầu ra giống hệt từng byte. Với cùng một artifact, phép băm mật mã như SHA-256 phải cho cùng giá trị.

Ví dụ:

- Lần build thứ nhất tạo file app.jar có SHA-256 là H.
- Một lần build độc lập trên workspace sạch tạo app.jar thứ hai.
- Nếu hai file giống hệt từng byte, SHA-256 của chúng giống nhau và phép so sánh nhị phân không tìm thấy khác biệt.

Một build tái lập được không chỉ có nghĩa là "lệnh chạy thành công". Nó chứng minh đầu ra không phụ thuộc vào những yếu tố biến động ngoài tập đầu vào được kiểm soát.

### Bảng phân biệt

| Tiêu chí | Build chạy lại được | Build tái lập từng byte |
|---|---|---|
| Mục tiêu | Có thể chạy lại quy trình và hoàn tất | Tạo cùng nội dung đầu ra qua các lần build độc lập |
| Điều kiện | Lệnh, công cụ và môi trường đủ để chạy | Đầu vào, công cụ, môi trường và bước tạo artifact được kiểm soát |
| Kết quả | Có thể thành công nhưng file khác nhau | Artifact tương ứng giống hệt từng byte |
| Timestamp | Có thể dùng thời gian hiện tại | Cần chuẩn hóa hoặc loại bỏ timestamp biến động |
| Dependency | Có thể tải phiên bản mới nếu khai báo động | Phiên bản và nội dung dependency phải được cố định, xác minh |
| Workspace | Có thể phụ thuộc trạng thái máy hiện tại | Phải kiểm soát trạng thái nguồn và dữ liệu trung gian |
| Bằng chứng | Log cho thấy lệnh build đã chạy thành công | Hash hoặc phép so sánh byte xác nhận đầu ra giống nhau |
| Giá trị | Giúp vận hành pipeline ổn định | Hỗ trợ xác minh nguồn gốc, kiểm toán và chuỗi cung ứng phần mềm |

Trong thực tế, thuật ngữ repeatable, reproducible và deterministic đôi khi được dùng khác nhau giữa các nhóm hoặc công cụ. Vì vậy, khi đặt tiêu chí chất lượng, hãy mô tả kết quả cần đạt bằng phép kiểm tra cụ thể: cùng commit và cùng tập đầu vào phải tạo ra cùng digest artifact.

## 2. Tính quyết định và tính tái lập

Một bước xử lý có tính quyết định (deterministic) khi cùng đầu vào và cùng trạng thái được kiểm soát luôn tạo ra cùng kết quả. Ví dụ, một compiler có thể biên dịch cùng source code thành cùng object file nếu phiên bản compiler, cờ biên dịch, đường dẫn và các đầu vào liên quan không đổi.

Tuy nhiên, một pipeline gồm nhiều bước có thể chứa một bước không quyết định. Chỉ cần một bước đưa dữ liệu biến động vào artifact, toàn bộ kết quả cuối có thể khác.

Có thể phân biệt ba phạm vi:

1. **Tái lập ở cấp bước:** từng công cụ hoặc task tạo cùng đầu ra khi đầu vào không đổi.
2. **Tái lập ở cấp build:** toàn bộ quy trình từ source đến artifact tạo cùng kết quả.
3. **Tái lập ở cấp phát hành:** artifact, metadata, manifest và các đầu ra được phát hành có thể được tạo lại hoặc xác minh theo quy tắc đã định nghĩa.

Một build có thể tái lập ở cấp binary nhưng metadata phát hành hoặc chữ ký được tạo ở bước sau lại thay đổi theo thời gian. Nhóm nên xác định rõ artifact nào cần so sánh: JAR, executable, container image, package, manifest hay toàn bộ release bundle.

### Ví dụ: hai file JAR có cùng mã lớp nhưng khác byte

Giả sử hai lần build tạo ra app.jar:

- Các file .class bên trong giống nhau.
- File MANIFEST.MF giống nhau.
- Nhưng timestamp của từng entry ZIP khác nhau.

Ứng dụng có thể chạy giống hệt, nhưng hai file JAR không giống nhau từng byte. Nếu chỉ chạy unit test hoặc kiểm tra hành vi, khác biệt này có thể không được phát hiện. Phép so sánh SHA-256 sẽ cho hai giá trị khác nhau.

Điều đó cho thấy cần phân biệt:

- **Tương đương chức năng:** ứng dụng thể hiện hành vi tương đương khi chạy.
- **Tái lập nội dung:** artifact giống nhau từng byte.

Tái lập từng byte là tiêu chí mạnh hơn và thường đòi hỏi kiểm soát metadata đóng gói, không chỉ mã nguồn.

## 3. Những nguồn gây khác biệt giữa hai lần build

Một build có thể bị ảnh hưởng bởi nhiều yếu tố tưởng như không liên quan tới mã nguồn. Nên phân nhóm chúng để tìm nguyên nhân.

### Thời gian và timestamp

Các công cụ có thể nhúng thời gian hiện tại vào:

- Metadata của JAR, ZIP, TAR hoặc package.
- File sinh tự động như version.properties hoặc build-info.json.
- Header, manifest hoặc thông tin debug.
- Container image config và layer metadata.
- Tên file, thư mục hoặc báo cáo build.

Nếu mỗi lần build lấy thời gian hệ thống, đầu ra sẽ khác ngay cả khi source không đổi.

### Dependency và công cụ có thể thay đổi

Các khai báo như phiên bản mới nhất, khoảng phiên bản hoặc tag mutable có thể tải nội dung khác ở hai lần chạy. Ví dụ:

- Dependency dùng phiên bản động như 1.+ hoặc latest.release.
- Container base image dùng tag latest.
- Plugin build không khóa phiên bản.
- Công cụ tải trực tiếp từ URL trỏ tới file có thể bị thay thế.
- Git submodule không được checkout theo commit mong muốn.
- Dependency được lấy từ repository không có checksum hoặc xác minh nội dung.

Tên và version giống nhau chưa chắc bảo đảm nội dung giống nhau nếu kho lưu trữ cho phép ghi đè artifact.

### Hệ điều hành và toolchain

Các yếu tố sau có thể làm đầu ra khác:

- Phiên bản JDK, compiler, linker hoặc build tool.
- Nhà cung cấp và bản vá của runtime.
- Phiên bản hệ điều hành và thư viện hệ thống.
- Kiến trúc CPU, cờ tối ưu hóa và instruction set.
- Phiên bản Docker/BuildKit hoặc công cụ đóng gói.
- Locale, timezone, encoding và quy tắc sắp xếp chuỗi.
- Umask, quyền file, owner/group và metadata filesystem.

Chỉ ghi "Java 21" đôi khi chưa đủ. Cần biết phiên bản toolchain thực tế và các thành phần ảnh hưởng tới bytecode hoặc artifact.

### Đường dẫn và trạng thái workspace

Đường dẫn tuyệt đối của workspace có thể xuất hiện trong debug information, generated source, manifest hoặc log được đóng gói. Ví dụ một build chạy tại /home/runner/work/project và lần khác chạy tại /builds/project có thể tạo binary khác nhau nếu compiler nhúng đường dẫn.

Workspace bẩn cũng gây sai khác:

- File sinh từ lần build trước còn tồn tại.
- File untracked vô tình được đưa vào package.
- Build lấy source chưa commit hoặc working tree đang dirty.
- Cache chứa dữ liệu cũ.
- Một task đọc file cấu hình nằm ngoài repository.

### Thứ tự xử lý và tính ngẫu nhiên

Một số khác biệt đến từ cách dữ liệu được duyệt hoặc task chạy song song:

- Thứ tự file lấy từ filesystem hoặc map không được cố định.
- Các task cùng ghi một đầu ra.
- Tên hoặc thứ tự thành phần được sinh từ collection không ổn định.
- Random seed không được khai báo.
- Mã sinh tự động dùng số ngẫu nhiên hoặc UUID.
- Test hoặc code generation phụ thuộc thời điểm hoàn thành của luồng bất đồng bộ.

### Dịch vụ và dữ liệu bên ngoài

Build có thể gọi API, truy vấn database, tải schema hoặc đọc thông tin từ một dịch vụ đang thay đổi. Nếu kết quả đó được đưa vào artifact, hai lần build có thể khác nhau dù source giống nhau.

Ví dụ: pipeline tạo file chứa tỷ giá hiện tại, danh sách feature flag hoặc kết quả truy vấn endpoint bên ngoài. Những giá trị đó là đầu vào thực tế của build và phải được cố định hoặc loại khỏi artifact nếu muốn tái lập.

## 4. Kiểm soát đầu vào của build

Muốn tái lập, trước hết phải biết chính xác build đã sử dụng những gì. Một build có thể được mô tả bằng tập đầu vào:

- Commit SHA của source repository.
- Commit của submodule và nội dung Git LFS nếu có.
- Dependency và checksum.
- Phiên bản compiler, runtime, build tool và plugin.
- Image nền hoặc môi trường thực thi.
- Các cờ build và biến môi trường có ảnh hưởng.
- File cấu hình, schema, code generator và dữ liệu đầu vào.
- Quy tắc đóng gói, timestamp và metadata.

### Dùng commit bất biến

CI nên checkout một commit cụ thể, không build từ trạng thái thay đổi của tên nhánh. Ghi lại commit SHA đầy đủ trong build metadata. Trước khi build, kiểm tra working tree không có thay đổi ngoài dự kiến.

Trong workspace CI dùng một lần, có thể tạo checkout mới cho từng lần build. Nếu cần làm sạch workspace cũ, chỉ chạy lệnh xóa trong thư mục CI đã xác định rõ, không áp dụng lên thư mục làm việc của nhà phát triển.

### Khóa dependency

Dùng cơ chế lock phiên bản và xác minh nội dung:

- Gradle dependency locking để ghi lại phiên bản dependency đã phân giải.
- Gradle dependency verification để kiểm tra checksum hoặc chữ ký theo cấu hình.
- Maven dùng version cụ thể cho dependency và plugin; quản lý parent POM và BOM rõ ràng.
- Node.js dùng lockfile như package-lock.json, pnpm-lock.yaml hoặc yarn.lock.
- Python dùng lock hoặc constraints có hash khi công cụ hỗ trợ.
- Container base image tham chiếu bằng digest khi cần xác định chính xác nội dung.

Không nên dùng version range hoặc tag mutable trong build phát hành. Nếu dependency được cập nhật, thay đổi đó cần đi qua một thay đổi được review và tạo ra lockfile hoặc manifest mới.

### Cố định công cụ build

Với dự án Java:

- Commit Gradle Wrapper hoặc Maven Wrapper.
- Khai báo phiên bản JDK/toolchain rõ ràng.
- Kiểm soát phiên bản plugin build.
- Ghi nhận phiên bản hệ điều hành hoặc image nền.
- Không dựa vào Gradle/Maven cài sẵn trên runner mà không xác định phiên bản.

Wrapper giúp chọn đúng phiên bản build tool, nhưng chưa đủ để khóa toàn bộ môi trường. JDK, dependency, plugin và thư viện hệ thống vẫn cần được kiểm soát.

### Kiểm soát nguồn ngoài repository

Nếu build cần schema, file binary, submodule hoặc dữ liệu do nhóm khác cung cấp, cần ghi nhận version hoặc digest của từng đầu vào. Tránh tải file "mới nhất" trong lúc build mà không lưu lại nội dung thực tế đã sử dụng.

Với dependency nội bộ, có thể dùng artifact repository có immutable version và checksum. Nếu repository hỗ trợ, bật chính sách ngăn ghi đè release đã phát hành.

## 5. Chuẩn hóa môi trường thực thi

Cùng source và dependency vẫn có thể tạo kết quả khác nếu môi trường khác nhau. Cần làm cho các yếu tố môi trường có ảnh hưởng được khai báo rõ.

### Cố định hệ điều hành và toolchain

Chọn runner image hoặc container image có phiên bản cụ thể. Ghi lại:

- OS image hoặc digest của container.
- JDK, compiler và build tool.
- Kiến trúc CPU.
- Phiên bản công cụ nén.
- Các biến môi trường liên quan tới build.

Alias như ubuntu-latest tiện dùng nhưng có thể trỏ sang image mới theo thời gian. Với build yêu cầu tái lập, nên dùng phiên bản image cụ thể và có quy trình cập nhật có kiểm soát.

### Chuẩn hóa locale và timezone

Locale có thể ảnh hưởng cách sắp xếp chuỗi, định dạng số hoặc ngày tháng. Timezone có thể làm timestamp được sinh khác nhau.

Một môi trường build thường đặt:

~~~sh
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TZ=UTC
umask 022
~~~

Cấu hình này giúp giảm khác biệt do locale, timezone và quyền file mặc định. Công cụ hoặc plugin vẫn có thể bỏ qua một số biến môi trường, vì vậy cần kiểm tra đầu ra thực tế.

### Chuẩn hóa đường dẫn

Nếu compiler hỗ trợ, dùng tùy chọn remap đường dẫn nguồn để không nhúng đường dẫn workspace cụ thể vào debug information. Ví dụ, một số compiler hỗ trợ các tùy chọn dạng prefix-map; tên và cú pháp phụ thuộc compiler.

Cũng cần tránh sinh file chứa đường dẫn tuyệt đối, tên máy hoặc username của người chạy. Nếu metadata đó cần cho chẩn đoán, lưu nó ở build log hoặc provenance bên ngoài artifact phát hành.

### Giới hạn ảnh hưởng từ môi trường ngoài

Một build hermetic (khép kín đầu vào) chỉ sử dụng các đầu vào đã khai báo. Nó không phụ thuộc ngẫu nhiên vào mạng, file trên máy hoặc dịch vụ đang thay đổi.

Có thể tiến tới hermetic build theo từng bước:

1. Resolve dependency trong bước chuẩn bị và lưu checksum.
2. Dùng dependency repository hoặc cache đã được kiểm soát.
3. Chạy build trong môi trường không cần tải nội dung không khai báo.
4. Hạn chế quyền đọc filesystem ngoài workspace.
5. Giới hạn network egress của job build khi phù hợp.
6. Ghi nhận các đầu vào thực tế để có thể tái tạo lần chạy.

Hermetic build hỗ trợ reproducibility, nhưng hai khái niệm không hoàn toàn đồng nhất. Một quy trình có thể dùng đầu vào được khai báo nhưng vẫn tạo timestamp hiện tại; khi đó đầu vào có vẻ được kiểm soát nhưng đầu ra vẫn không tái lập từng byte.

## 6. Loại bỏ timestamp và metadata biến động

Timestamp là một trong những nguyên nhân phổ biến nhất khiến archive và package khác nhau giữa hai lần build.

### SOURCE_DATE_EPOCH

SOURCE_DATE_EPOCH là biến môi trường được nhiều công cụ trong hệ sinh thái reproducible builds hỗ trợ. Nó cung cấp một mốc thời gian ổn định để công cụ dùng thay cho thời gian hiện tại khi tạo đầu ra.

Giá trị thường được lấy từ timestamp của commit nguồn hoặc một mốc đã được quy định trong quy trình phát hành. Quan trọng là cùng một source revision phải nhận cùng giá trị trong các lần build so sánh.

Ví dụ khái niệm:

~~~sh
export SOURCE_DATE_EPOCH=1704067200
./gradlew --no-daemon clean build
~~~

Giá trị trên chỉ minh họa một mốc Unix timestamp cố định. Trong pipeline thực tế, nên lấy mốc từ commit hoặc release metadata đã xác định, sau đó truyền nhất quán cho các công cụ hỗ trợ biến này.

Không phải công cụ nào cũng tự động đọc SOURCE_DATE_EPOCH. Cần kiểm tra tài liệu của compiler, archive tool, packager và plugin đang sử dụng. Nếu một plugin bỏ qua biến này, timestamp vẫn có thể thay đổi.

### Chuẩn hóa archive

JAR và ZIP có metadata cho từng entry. Để tăng khả năng tái lập, cần:

- Dùng thứ tự entry ổn định.
- Chuẩn hóa timestamp của entry.
- Chuẩn hóa quyền file khi định dạng hỗ trợ.
- Tránh đưa file tạm hoặc file sinh ngoài ý muốn vào archive.
- Cố định phiên bản công cụ nén và cấu hình compression nếu nó ảnh hưởng byte đầu ra.

Ví dụ với Gradle Kotlin DSL:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Các thuộc tính này giúp Gradle tạo archive với thứ tự file ổn định và không giữ timestamp gốc của file đầu vào. Chúng là một phần của giải pháp; plugin khác, nội dung file và metadata bổ sung vẫn cần được kiểm tra.

### Maven output timestamp

Với Maven, các phiên bản plugin hỗ trợ reproducible archive có thể sử dụng thuộc tính project.build.outputTimestamp. Ví dụ cấu hình:

~~~xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Đây là mốc cố định minh họa. Trong quy trình thực tế, nên cung cấp mốc được suy ra từ source revision theo cách nhất quán. Cần dùng phiên bản plugin hỗ trợ thuộc tính này và xác minh các plugin đóng gói khác cũng không chèn timestamp hiện tại.

## 7. Kiểm soát code generation và dữ liệu sinh tự động

Code generation thường tạo ra file source hoặc resource từ schema, template, API definition hoặc dữ liệu. Nếu generator dùng thời gian hiện tại, thứ tự đầu vào không ổn định hoặc version khác nhau, đầu ra sẽ khác.

Các biện pháp:

- Cố định phiên bản generator và plugin.
- Cố định schema, template và file đầu vào bằng commit hoặc digest.
- Sắp xếp đầu vào trước khi đưa vào generator.
- Dùng random seed cố định nếu generator có tính ngẫu nhiên và hỗ trợ seed.
- Loại timestamp hoặc build number khỏi nội dung được phát hành.
- Không lấy dữ liệu từ API thay đổi trong lúc build.
- Ghi lại lệnh và cấu hình generator để có thể chạy lại độc lập.

Nếu file sinh tự động được commit vào repository, cần quy định cách cập nhật và kiểm tra file đó khớp với generator. Nếu file được sinh trong CI, nên lưu phiên bản generator và đầu vào trong provenance để điều tra sai khác.

## 8. Container image cũng cần tái lập

Container image không chỉ là tập file ứng dụng. Image còn có manifest, config, layer, metadata và timestamp. Hai image có cùng nội dung ứng dụng vẫn có thể có digest khác nếu layer hoặc metadata khác.

Các nguồn khác biệt thường gặp:

- Base image dùng tag mutable như latest.
- Package manager cài phiên bản mới nhất tại thời điểm build.
- File được copy vào image giữ timestamp từ workspace.
- Thứ tự file hoặc layer thay đổi.
- Build argument chứa thời gian hoặc build ID.
- Metadata của image được tạo từ thời điểm hiện tại.
- Công cụ build image hoặc phiên bản BuildKit thay đổi.

### Pin base image bằng digest

Ví dụ:

~~~dockerfile
FROM eclipse-temurin:21-jre@sha256:<base-image-digest>

WORKDIR /app
COPY app.jar /app/app.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Digest xác định chính xác nội dung base image được tham chiếu. Tag giúp con người nhận biết phiên bản, nhưng digest mới là định danh nội dung. Cần thay placeholder bằng digest thật từ registry đáng tin cậy.

### Giữ đầu vào image ổn định

- Pin base image bằng digest.
- Khóa phiên bản package cài trong Dockerfile.
- Dùng package repository hoặc snapshot có nội dung cố định.
- Kiểm soát timestamp, quyền file và thứ tự tạo layer.
- Dùng cùng phiên bản builder và cấu hình build.
- Không truyền secret hoặc thông tin cá nhân vào build argument hay layer.
- Ghi nhận digest image và provenance của lần build.

Một container image có thể chứa JAR tái lập được nhưng bản thân image vẫn không tái lập. Vì vậy, nên kiểm tra cả digest của artifact ứng dụng lẫn digest OCI image cuối cùng.

## 9. Build một lần và kiểm chứng bằng build độc lập

Để chứng minh một artifact tái lập, cần ít nhất hai lần build độc lập với đầu vào được kiểm soát.

Quy trình tham khảo:

1. Chọn commit SHA cụ thể.
2. Tạo hai workspace sạch, độc lập.
3. Cấp cùng toolchain, dependency, cấu hình và biến môi trường.
4. Chạy cùng lệnh build.
5. Thu thập artifact từ cả hai lần chạy.
6. Tính SHA-256 của từng artifact.
7. So sánh hash; nếu khác, phân tích cấu trúc và byte khác biệt.
8. Lưu log, metadata và kết quả so sánh.

Hai lần build nên diễn ra trên runner hoặc workspace độc lập. Nếu cả hai dùng chung cache, thư mục build hoặc artifact trung gian, chúng có thể cùng dựa vào một dữ liệu cũ và không thực sự kiểm tra tính tái lập.

### So sánh bằng hash

Trên Linux:

~~~sh
sha256sum build-a/app.jar
sha256sum build-b/app.jar
cmp build-a/app.jar build-b/app.jar
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash build-a/app.jar -Algorithm SHA256
Get-FileHash build-b/app.jar -Algorithm SHA256
fc.exe /b build-a/app.jar build-b/app.jar
~~~

fc.exe /b là phép so sánh nhị phân có sẵn trên Windows. Nếu hash giống nhau, hai file có cùng nội dung theo phép băm được dùng. Nếu hash khác nhau, chưa thể kết luận mã nguồn hoặc hành vi khác; cần tìm vị trí khác biệt.

### Dùng diffoscope để tìm nguyên nhân

diffoscope giúp phân tích hai file khác nhau ở nhiều định dạng. Với JAR hoặc ZIP, nó có thể đi sâu vào entry; với binary, nó có thể hiển thị khác biệt cấu trúc khi có công cụ hỗ trợ.

Một quy trình điều tra:

1. So sánh hash của artifact tổng thể.
2. Liệt kê nội dung archive và so sánh danh sách entry.
3. So sánh metadata timestamp, quyền và thứ tự file.
4. Giải nén vào hai thư mục riêng rồi so sánh file bên trong.
5. Dùng diffoscope để tìm byte hoặc metadata khác nhau.
6. Truy ngược file khác biệt tới task hoặc plugin tạo ra nó.

Không nên chỉ sửa để hai hash giống nhau bằng cách xóa tùy tiện metadata. Cần xác định metadata đó có cần cho runtime, bảo mật, debug hoặc truy vết hay không.

## 10. Tích hợp kiểm tra reproducibility vào CI

Có thể bắt đầu bằng một job kiểm tra build thông thường, sau đó bổ sung một lần build độc lập để so sánh artifact. Với workload lớn, không nhất thiết chạy hai build cho mọi commit; có thể áp dụng cho release, nhánh chính hoặc theo lịch tùy chi phí và mức rủi ro.

### Luồng CI tham khảo

~~~text
Commit SHA
    |
    v
Resolve locked dependencies
    |
    v
Build A on clean runner A
    |
    +--------------------+
    |                    |
    v                    v
Build B on clean runner B
    |                    |
    v                    v
Artifact A            Artifact B
    |                    |
    +----------+---------+
               |
               v
       Compare SHA-256
               |
        +------+------+
        |             |
      Equal        Different
        |             |
        v             v
  Reproducible    Investigate diff
  check passed    and fail gate
~~~

Hai job phải dùng cùng commit SHA và cùng tập đầu vào đã khóa. Nếu runner khác hệ điều hành hoặc kiến trúc, khác biệt có thể là kết quả cần phát hiện hoặc một môi trường không nằm trong phạm vi tái lập mà dự án cam kết. Hãy định nghĩa rõ phạm vi so sánh.

### Ví dụ cấu hình kiểm tra hai lần build

Một pipeline có thể chia thành các job:

~~~yaml
jobs:
  build_a:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.sha }}
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon clean build
      - run: mkdir -p reproducibility && cp build/libs/app.jar reproducibility/app.jar
      - run: sha256sum reproducibility/app.jar > reproducibility/app.sha256
      - uses: actions/upload-artifact@v4
        with:
          name: reproducibility-a
          path: reproducibility/

  build_b:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.sha }}
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon clean build
      - run: mkdir -p reproducibility && cp build/libs/app.jar reproducibility/app.jar
      - run: sha256sum reproducibility/app.jar > reproducibility/app.sha256
      - uses: actions/upload-artifact@v4
        with:
          name: reproducibility-b
          path: reproducibility/

  compare:
    needs: [build_a, build_b]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: reproducibility-a
          path: result-a
      - uses: actions/download-artifact@v4
        with:
          name: reproducibility-b
          path: result-b
      - run: cmp result-a/app.jar result-b/app.jar
~~~

Ví dụ này minh họa cấu trúc. Trong workflow thật, cần điều chỉnh đường dẫn JAR, task Gradle, tên artifact và phiên bản action theo dự án. Hai job dùng cùng runner image và cùng SHA, nhưng vẫn có workspace riêng. Để tăng độ tin cậy, có thể dùng hai pool runner độc lập hoặc builder độc lập có cấu hình được ghi nhận.

Nếu build cần dependency, cả hai job phải resolve cùng nội dung dependency đã khóa. Cache chỉ được dùng để tăng tốc; cache không được phép thay thế lock file hoặc checksum. Khi kiểm tra lần đầu, có thể chạy không dùng cache để phát hiện sự phụ thuộc vào trạng thái cache.

### Xử lý khi so sánh thất bại

Nếu cmp trả về khác biệt, job compare phải thất bại để kết quả không bị hiểu nhầm là reproducible. Nên lưu cả hai artifact, hash, log và metadata phục vụ điều tra. Sau khi sửa nguyên nhân, chạy lại trên workspace sạch để xác nhận.

Không nên dùng điều kiện luôn thành công hoặc bỏ qua lỗi so sánh chỉ để pipeline xanh. Nếu có artifact cố ý chứa metadata biến động, cần tách metadata đó ra hoặc định nghĩa rõ phạm vi artifact được kiểm chứng.

## 11. Reproducibility và provenance: hai bằng chứng bổ sung nhau

Build tái lập và build provenance giải quyết hai câu hỏi khác nhau:

- **Reproducibility:** với cùng đầu vào và quy trình, có thể tạo ra cùng artifact hay không?
- **Provenance:** artifact được tạo từ source nào, bởi builder nào, dùng công cụ và dependency nào, trong pipeline run nào?

Một artifact có thể tái lập nhưng được build từ source độc hại. Ngược lại, một artifact có provenance đầy đủ vẫn có thể không tái lập nếu build nhúng timestamp hoặc dữ liệu biến động.

Một bản ghi provenance nên có:

- Repository và commit SHA.
- Phiên bản build tool, compiler và runtime.
- Digest của container image hoặc runner image.
- Dependency lock file và checksum.
- Các cờ build, biến môi trường quan trọng.
- Pipeline run ID và danh tính builder.
- Artifact URI, version và digest.
- Kết quả kiểm tra reproducibility.
- Chữ ký hoặc attestation nếu hệ thống hỗ trợ.

Không đưa secret, token hoặc dữ liệu nhạy cảm vào provenance. Có thể ký attestation bằng khóa được bảo vệ hoặc danh tính workload ngắn hạn, sau đó xác minh chữ ký trước khi phát hành.

### Reproducible build không thay thế kiểm tra bảo mật

Hai lần build tạo cùng binary chỉ cho biết quy trình tái tạo đầu ra nhất quán theo đầu vào đã khai báo. Điều đó không chứng minh dependency an toàn, source được review đầy đủ hoặc compiler không bị xâm nhập.

Nên kết hợp:

- Dependency scanning và kiểm tra license.
- Static analysis và test.
- Xác minh checksum/signature của dependency.
- Kiểm tra provenance của builder.
- Bảo vệ pipeline definition và runner.
- Review thay đổi toolchain và lock file.
- Lưu artifact bất biến cùng digest.

## 12. Chữ ký số và những đầu ra có chủ đích thay đổi

Chữ ký số có thể chứa timestamp từ dịch vụ đóng dấu thời gian, thông tin chứng thư hoặc dữ liệu ngẫu nhiên. Vì vậy, hai lần ký cùng một binary có thể tạo ra file chữ ký khác nhau, ngay cả khi binary không đổi.

Một cách tổ chức thường dùng:

1. Build artifact theo quy trình tái lập.
2. Tính và lưu digest của artifact chưa ký.
3. Kiểm chứng reproducibility trên artifact đó.
4. Ký artifact hoặc tạo attestation ở bước phát hành riêng.
5. Lưu chữ ký và metadata ký tách biệt hoặc liên kết bằng digest.

Không phải mọi chữ ký đều không thể tái lập; điều này phụ thuộc thuật toán, định dạng và cách ký. Nhưng nếu quy trình ký có timestamp bên ngoài hoặc thông tin chứng thư thay đổi, không nên dùng toàn bộ file chữ ký làm tiêu chí so sánh binary. Hãy xác định chính xác phần nội dung nào cần tái lập.

Các dữ liệu như build number, thời gian phát hành, người phê duyệt hoặc release note cũng có thể thay đổi có chủ đích. Nên tách chúng khỏi artifact bất biến nếu không cần nhúng vào runtime package, hoặc quản lý chúng trong manifest phát hành riêng.

## 13. Các cấp độ thực hành và lộ trình triển khai

Không cần biến mọi dự án thành một hệ thống hermetic phức tạp ngay lập tức. Có thể tiến triển theo mức độ:

| Mức | Thực hành | Kết quả |
|---|---|---|
| 1. Có thể chạy lại | Lệnh build chuẩn, workspace sạch, log rõ | Nhóm có thể thực thi lại quy trình |
| 2. Khóa đầu vào | Commit cụ thể, dependency lock, toolchain cố định | Giảm khác biệt do phiên bản và trạng thái ngoài |
| 3. Chuẩn hóa môi trường | Image cụ thể, locale/timezone, timestamp và đường dẫn ổn định | Giảm nguồn nondeterminism |
| 4. Build khép kín | Đầu vào được khai báo, hạn chế truy cập mạng và filesystem ngoài | Tăng khả năng tái tạo độc lập |
| 5. Kiểm chứng từng byte | Hai build độc lập, hash và diffoscope | Có bằng chứng artifact tái lập |
| 6. Gắn provenance | Lưu source, builder, dependency, digest và attestation | Có thể xác minh chuỗi tạo artifact |

### Lộ trình cho dự án Java

1. Chuẩn hóa lệnh build bằng Gradle Wrapper hoặc Maven Wrapper.
2. Cố định JDK/toolchain và phiên bản plugin.
3. Bật dependency locking hoặc khai báo dependency version cụ thể.
4. Bật dependency verification khi hệ sinh thái hỗ trợ.
5. Chuẩn hóa archive timestamp và file order.
6. Dùng workspace sạch và cố định source commit.
7. Chạy hai build độc lập rồi so sánh JAR bằng SHA-256.
8. Khi hash khác, dùng diffoscope hoặc giải nén archive để tìm metadata thay đổi.
9. Lưu kết quả cùng commit SHA và artifact digest.
10. Áp dụng kiểm tra nghiêm ngặt cho release sau khi quy trình ổn định.

## 14. Những lỗi thường gặp

| Cách làm | Vấn đề | Cách cải thiện |
|---|---|---|
| Chạy lại build và thấy thành công nên kết luận reproducible | Chỉ chứng minh lệnh chạy được | So sánh artifact từng byte |
| Dùng dependency version động | Hai lần build có thể tải nội dung khác | Lock version và checksum |
| Dùng container tag latest | Base image có thể thay đổi | Pin digest |
| Nhúng thời gian hiện tại vào file | Mỗi lần build tạo byte khác | Dùng timestamp ổn định hoặc tách metadata |
| Không chuẩn hóa file order | Archive có thể thay đổi thứ tự entry | Sắp xếp entry ổn định |
| Build từ workspace bẩn | File cũ hoặc untracked lọt vào package | Dùng checkout sạch và kiểm soát trạng thái |
| Chia sẻ cache giữa job không cùng trust zone | Cache có thể làm sai hoặc nhiễm dữ liệu | Phân vùng cache và xác minh dependency |
| Chỉ kiểm tra JAR nhưng bỏ qua container image | Image metadata hoặc layer vẫn thay đổi | Kiểm tra cả digest package và image |
| So sánh file đã ký có timestamp động | Chữ ký khác dù binary giống | Kiểm chứng binary trước bước ký |
| Chỉ lưu hash mà không lưu đầu vào | Không thể điều tra vì sao hash thay đổi | Lưu provenance và build metadata |
| Dùng cùng workspace cho hai lần build | Có thể chia sẻ trạng thái trung gian | Dùng runner/workspace độc lập |

## 15. Checklist xác minh build tái lập

### Đầu vào

- [ ] Build checkout một commit SHA cụ thể.
- [ ] Working tree sạch và không chứa thay đổi ngoài dự kiến.
- [ ] Submodule, Git LFS và file sinh tự động được xác định rõ.
- [ ] Dependency và plugin được khóa phiên bản.
- [ ] Nội dung dependency được xác minh bằng checksum hoặc chữ ký khi có thể.
- [ ] Container base image được pin bằng digest nếu sử dụng.

### Môi trường và quy trình

- [ ] Phiên bản OS, JDK, compiler và build tool được ghi nhận.
- [ ] Locale, timezone, encoding và umask được chuẩn hóa khi có ảnh hưởng.
- [ ] Timestamp và build metadata biến động được loại bỏ hoặc cố định.
- [ ] Thứ tự file trong archive được xác định ổn định.
- [ ] Đường dẫn tuyệt đối và dữ liệu máy cá nhân không bị nhúng ngoài ý muốn.
- [ ] Build không phụ thuộc dữ liệu hoặc dịch vụ bên ngoài thay đổi.

### Kiểm chứng đầu ra

- [ ] Hai lần build dùng workspace độc lập.
- [ ] Hai lần build dùng cùng tập đầu vào đã khai báo.
- [ ] Artifact được so sánh bằng SHA-256 hoặc phép so sánh byte.
- [ ] Nếu hash khác, có log và công cụ phân tích để tìm nguyên nhân.
- [ ] Kết quả kiểm chứng được lưu cùng commit SHA và artifact digest.
- [ ] Chữ ký và metadata phát hành được đánh giá theo phạm vi riêng.

## Kết luận

Build chạy lại được giúp nhóm thực thi lại quy trình; build tái lập từng byte chứng minh cùng đầu vào và quy trình có thể tạo ra cùng artifact qua các lần chạy độc lập. Để đạt được điều đó, cần khóa dependency, cố định toolchain, chuẩn hóa môi trường, kiểm soát timestamp và metadata, loại bỏ nguồn dữ liệu biến động, rồi kiểm chứng bằng hash trên hai build sạch. Khi kết hợp kết quả đó với provenance và artifact bất biến, nhóm có thể xác minh tốt hơn nguồn gốc, tính toàn vẹn và khả năng tái tạo của gói phát hành trong toàn bộ vòng đời CI/CD.

