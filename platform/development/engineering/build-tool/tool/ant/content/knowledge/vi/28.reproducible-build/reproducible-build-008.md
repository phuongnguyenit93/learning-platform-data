# Cân bằng tính tái lập với thông tin thời điểm phát hành trong Apache Ant

## 1. Một bản phát hành cần hai loại sự thật

Giả sử nhóm phát triển dùng Apache Ant để tạo tệp JAR từ cùng một commit Git. Lần đóng gói thứ nhất thực hiện lúc 09:00, lần thứ hai lúc 15:00. Nếu mã nguồn, thư viện, công cụ và cấu hình giống hệt nhau, mục tiêu của **build tái lập** (*reproducible build*) là hai tệp JAR có cùng nội dung byte và cùng mã băm SHA-256.

Tuy nhiên, nhóm phát hành vẫn cần biết bản phát hành được công bố lúc nào, pipeline nào đã duyệt nó, ai phê duyệt và khi nào nó được triển khai. Những thông tin này thay đổi theo **sự kiện phát hành**, dù mã nguồn không đổi. Nếu ghi giờ hiện tại vào JAR mỗi lần build, nhóm sẽ làm mất khả năng so sánh hai artifact bằng mã băm.

Vì vậy cần phân biệt:

- **Định danh của artifact:** được xác định bởi đầu vào build; có thể kiểm chứng và tái tạo.
- **Nhật ký sự kiện phát hành:** mô tả một lần công bố, ký, phân phối hoặc triển khai artifact; có thời điểm thực tế.

Một artifact có thể được build một lần rồi phát hành qua nhiều môi trường. Mỗi sự kiện có dấu thời gian riêng, trong khi byte của artifact vẫn giữ nguyên.

### Ba khái niệm thời gian không được đánh đồng

| Khái niệm | Ý nghĩa | Tính ổn định | Nơi lưu phù hợp |
|---|---|---|---|
| **Thời điểm nguồn** (*source timestamp*) | Mốc đã chọn từ mã nguồn, commit hoặc lịch phát hành để chuẩn hóa metadata | Cố định với cùng đầu vào | Cấu hình build, timestamp chuẩn hóa trong JAR/ZIP |
| **Thời điểm thực thi build** (*build execution time*) | Lúc một job thực sự chạy lệnh Ant | Thay đổi giữa các lần chạy | Nhật ký CI, hệ thống theo dõi job |
| **Thời điểm công bố** (*publishedAt / releasedAt*) | Lúc kho artifact hoặc quy trình phát hành xác nhận đã công bố | Thay đổi theo từng sự kiện | Release record, registry, metadata bên ngoài JAR |

Thời điểm một hệ thống **triển khai** artifact (*deployedAt*) còn là một mốc khác. Nó thuộc bản ghi triển khai của từng môi trường, không phải thuộc tính nội tại của tệp JAR.

## 2. Vì sao đưa thời gian hiện tại vào JAR phá hủy tính tái lập?

Ví dụ Ant sau thường xuất hiện trong dự án muốn hiển thị “Build-Time”:

~~~xml
<target name="package">
    <tstamp>
        <format property="build.time"
                pattern="yyyy-MM-dd'T'HH:mm:ss'Z'"
                timezone="UTC"/>
    </tstamp>

    <jar destfile="dist/app.jar" basedir="build/classes">
        <manifest>
            <attribute name="Build-Time" value="${build.time}"/>
        </manifest>
    </jar>
</target>
~~~

Theo mặc định, tác vụ **tstamp** lấy thời gian hiện tại. Lần chạy sau tạo giá trị “Build-Time” khác, làm thay đổi nội dung **META-INF/MANIFEST.MF** và mã băm của JAR. Việc chuyển sang UTC chỉ cố định múi giờ hiển thị, không cố định giá trị thời gian.

Thậm chí khi không khai báo “Build-Time”, JAR/ZIP vẫn có thể khác nhau vì thời gian sửa đổi của từng entry trong archive. File biên dịch hoặc tài nguyên được tạo ở thời điểm khác sẽ mang metadata thời gian khác, trừ khi được chuẩn hóa. Các nguyên nhân biến thiên khác gồm phiên bản JDK/Ant, dependency không được chốt phiên bản, dữ liệu sinh ngẫu nhiên, thứ tự file, encoding, locale hoặc đường dẫn máy build bị ghi vào sản phẩm.

Như vậy, **bỏ trường Build-Time mới chỉ xử lý một nguồn bất ổn**; muốn hai lần build ra cùng SHA-256 còn cần kiểm soát các đầu vào và metadata khác.

## 3. Quy tắc thiết kế: cố định dữ liệu thuộc artifact, tách dữ liệu thuộc sự kiện

| Thông tin | Có thể nhúng trong JAR? | Cách xử lý |
|---|---|---|
| Tên ứng dụng, phiên bản phát hành | Có | Lấy từ cấu hình phiên bản cố định của lần build |
| Commit Git hoặc revision của nguồn | Có | Cung cấp từ checkout đã chốt; cùng commit phải cho cùng giá trị |
| Timestamp chuẩn hóa của ZIP/JAR entry | Có | Chọn một giá trị xác định, bất biến cho cùng bộ đầu vào |
| Phiên bản Ant, JDK, dependency | Có thể ghi nhận | Khóa trong môi trường build; ghi thêm vào build provenance nếu cần |
| Giờ job CI bắt đầu/kết thúc | Nên lưu ngoài JAR | Ghi trong log và build record |
| Số lần chạy pipeline, URL job, người phê duyệt | Nên lưu ngoài JAR | Gắn với lần thực thi hoặc release record |
| Giờ artifact được công bố, promote, deploy | Lưu ngoài JAR | Registry, release record, deployment history |

Có thể hình dung luồng dữ liệu như sau:

~~~text
Commit + nguồn + dependency khóa + toolchain + phiên bản
                 + timestamp chuẩn hóa
                           |
                           v
                  Apache Ant build
                           |
                           v
                 app.jar (SHA-256 = H)
                           |
             +-------------+-------------+
             |                           |
             v                           v
       Release staging             Release production
       artifact hash H             artifact hash H
       publishedAt T1              publishedAt T2
       deployment D1               deployment D2
~~~

Mã băm **H** mô tả tệp phát hành. Các mốc **T1**, **T2** mô tả hoạt động xảy ra với tệp đó. Khi promote một artifact đã kiểm chứng qua các môi trường, không cần biên dịch lại chỉ để đổi ngày triển khai.

## 4. Xây dựng một JAR có timestamp ổn định bằng Ant

Ví dụ dưới đây giả định dự án đơn giản, chỉ dùng thư viện chuẩn Java, chạy trên **Apache Ant 1.10.2 trở lên** với JDK hỗ trợ Java 17. Thuộc tính **modificationtime** của tác vụ **jar** có từ Ant 1.10.2; thuộc tính này đặt thời gian sửa đổi được lưu cho các entry trong archive. Với dự án thực tế, cần khóa thêm version và checksum của dependency ngoài.

### 4.1. Cấu trúc mẫu

~~~text
demo/
├── build.xml
├── release-inputs.properties
└── src/
    └── example/
        └── App.java
~~~

Trong **release-inputs.properties**, ba giá trị là đầu vào có chủ đích, không được tự thay bằng đồng hồ của máy build:

~~~properties
release.version=1.3.0
source.revision=0123456789abcdef0123456789abcdef01234567
archive.timestamp=2024-01-01T00:00:00Z
~~~

Revision trên chỉ là giá trị minh họa; khi triển khai thực tế phải thay bằng commit đã được chọn để build. Mốc archive có thể lấy từ một commit, một mốc chuẩn do nhóm quy định, hoặc từ một quy tắc xác định khác. Điều kiện là **hai lần build cùng đầu vào chọn cùng mốc**. Giá trị này không tuyên bố sản phẩm đã được phát hành vào ngày 01/01/2024.

Tệp **src/example/App.java**:

~~~java
package example;

public final class App {
    public static void main(String[] args) {
        System.out.println("Hello from Apache Ant");
    }
}
~~~

Tệp **build.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-reproducible-demo" default="package" basedir=".">
    <property file="release-inputs.properties"/>

    <property name="src.dir" location="src"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="artifact.file" location="build/dist/demo.jar"/>

    <target name="validate">
        <fail unless="release.version" message="Missing release.version"/>
        <fail unless="source.revision" message="Missing source.revision"/>
        <fail unless="archive.timestamp" message="Missing archive.timestamp"/>
    </target>

    <target name="clean">
        <delete dir="build"/>
    </target>

    <target name="compile" depends="validate">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               release="17"
               encoding="UTF-8"
               includeantruntime="false"
               debug="false"/>
    </target>

    <target name="package" depends="compile">
        <mkdir dir="build/dist"/>
        <jar destfile="${artifact.file}"
             basedir="${classes.dir}"
             update="false"
             duplicate="fail"
             encoding="UTF8"
             modificationtime="${archive.timestamp}">
            <manifest>
                <attribute name="Implementation-Title" value="Ant Demo"/>
                <attribute name="Implementation-Version"
                           value="${release.version}"/>
                <attribute name="Source-Revision"
                           value="${source.revision}"/>
            </manifest>
        </jar>
    </target>
</project>
~~~

Điểm cần hiểu trong cấu hình:

1. **release-inputs.properties** định nghĩa những giá trị mà artifact được phép chứa. Cùng source revision, version và archive timestamp phải được đưa vào cả hai lần build đối chiếu.
2. **modificationtime** chuẩn hóa thời điểm của entry trong JAR. Đây là thời gian kỹ thuật nhằm tái lập archive; không phải “ngày công bố”.
3. **Implementation-Version** và **Source-Revision** là những định danh ổn định, hữu ích khi truy vết một JAR đã nhận.
4. **release="17"**, **encoding="UTF-8"** và **includeantruntime="false"** giảm phụ thuộc vào mặc định của máy chạy Ant. Muốn kết quả byte-for-byte ổn định vẫn phải dùng cùng phiên bản toolchain và cùng môi trường biên dịch đã chốt.
5. **update="false"** tránh chủ đích cập nhật nội dung từ một archive cũ; mỗi lần đối chiếu nên chạy trên workspace sạch để không mang class hoặc tài nguyên thừa từ lần build trước.

Trong ví dụ, file properties và revision phải được quản lý bởi quy trình có khả năng xác minh. Nếu CI truyền giá trị qua tham số **-D**, Ant có thể dùng giá trị đó thay cho file properties; bởi vậy tham số CI cũng là một phần của bộ đầu vào cần ghi nhận và cố định.

### 4.2. Các mốc trong ZIP/JAR không tự đồng bộ với SOURCE_DATE_EPOCH

Hệ sinh thái reproducible builds thường dùng biến môi trường **SOURCE_DATE_EPOCH**: số giây tính từ Unix epoch, biểu diễn một thời điểm nguồn cố định. Apache Ant hỗ trợ:

- Với **tstamp**, từ Ant **1.10.8**, khi biến môi trường SOURCE_DATE_EPOCH hợp lệ được đặt, tác vụ sẽ sử dụng nó thay cho giờ thực hiện build.
- Từ Ant **1.10.18**, khi tstamp lấy thời gian từ SOURCE_DATE_EPOCH, các định dạng mặc định sử dụng UTC (và locale mặc định cho format lồng bên trong là en_US nếu không đặt tường minh).
- Với **jar** và **zip**, thuộc tính **modificationtime** nhận thời điểm theo ISO-8601 hoặc số **mili giây** kể từ epoch; đây là cấu hình riêng của archive. Không được giả định chỉ đặt SOURCE_DATE_EPOCH là mọi entry JAR/ZIP đã tự có timestamp chuẩn hóa.

Điểm dễ nhầm là **SOURCE_DATE_EPOCH có đơn vị giây**, trong khi giá trị dạng số của **modificationtime** là **mili giây**. Không truyền trực tiếp chuỗi số giây của biến môi trường vào modificationtime. Ví dụ ở trên dùng ISO-8601 UTC để tránh nhầm đơn vị. Nếu công cụ CI lấy mốc nguồn từ commit rồi tạo timestamp ISO-8601, bước chuyển đổi đó phải nhất quán và có thể lặp lại.

Hơn nữa, khi tstamp đã chịu ảnh hưởng của SOURCE_DATE_EPOCH, giá trị tạo ra từ tstamp là **mốc được kiểm soát cho build**, không nhất thiết là thời điểm phát hành thực tế. Vì vậy không nên dùng chính giá trị đó để ghi “publishedAt” trong registry.

## 5. Lưu thời điểm phát hành thực tế ở đâu?

Sau khi Ant tạo JAR và quy trình đã xác minh artifact, hệ thống phát hành có thể tạo một bản ghi bên ngoài JAR, ví dụ **release-info.json**:

~~~json
{
  "application": "ant-demo",
  "version": "1.3.0",
  "sourceRevision": "0123456789abcdef0123456789abcdef01234567",
  "artifact": "demo.jar",
  "artifactSha256": "<sha256-do-he-thong-phat-hanh-tinh>",
  "publishedAt": "2026-11-13T02:30:00Z",
  "releaseChannel": "production",
  "releaseId": "release-2026-11-13-01"
}
~~~

Đây là **mẫu cấu trúc dữ liệu**, không phải kết quả thực tế của ví dụ Ant. Trường publishedAt phải do hệ thống xác nhận phát hành điền tại thời điểm công bố thật; artifactSha256 phải được tính từ **byte của JAR đã được kiểm chứng**. Chẳng hạn release registry có thể lưu record này cùng release assets, hoặc hệ thống triển khai có thể lưu nó trong deployment history.

Một workflow thực tế thường làm theo thứ tự:

1. Lấy đúng commit đã được duyệt; khóa cấu hình Ant, JDK, dependency và thông số build.
2. Chạy Ant để tạo JAR; tính SHA-256; kiểm chứng kết quả, kiểm thử và xác định artifact đủ điều kiện phát hành.
3. Đưa **chính artifact đã kiểm chứng** lên kho phát hành; xác nhận kho đã chấp nhận artifact với đúng mã băm.
4. Ghi publishedAt theo sự kiện thành công, kèm revision, version, mã băm, release ID và thông tin phê duyệt cần thiết.
5. Khi promote sang môi trường khác, tham chiếu lại mã băm artifact và ghi **deployedAt** mới theo môi trường; không nhúng timestamp mới rồi build lại.

Sự khác biệt giữa **thời điểm tạo bản ghi dự kiến phát hành** và **thời điểm công bố đã thành công** cần được thể hiện rõ. Nếu upload hoặc phê duyệt thất bại, không ghi trạng thái “đã phát hành” chỉ vì pipeline đã bắt đầu. Nếu cùng một release được retry, sử dụng release ID hoặc một khóa định danh ổn định để tránh sinh các bản ghi công bố trùng hoặc làm mất dấu vết retry.

### Còn nếu bắt buộc hiển thị ngày build trong ứng dụng?

Trước tiên cần xác định yêu cầu thực sự:

- Nếu người dùng cần biết **mã nào đang chạy**, hiển thị version, revision và checksum đã xác thực là đủ mạnh để truy vết.
- Nếu người vận hành cần biết **khi nào artifact được công bố**, ứng dụng có thể đọc release metadata từ hệ thống triển khai hoặc một tài nguyên cấu hình runtime được phát hành riêng.
- Nếu chỉ cần **mốc nguồn ổn định**, có thể nhúng trường “Source-Date” hoặc “Reproducible-Epoch” được mô tả rõ, nhưng không gọi nó là thời điểm build/phát hành thực tế.

Nếu yêu cầu sản phẩm bắt buộc nhúng **giờ build hiện tại** vào JAR, cần chấp nhận rằng mỗi lần build sẽ có nội dung và SHA-256 khác nhau. Có thể coi đó là một artifact mới và quản lý rõ sự đánh đổi, thay vì tuyên bố build này byte-for-byte tái lập.

## 6. Kiểm chứng tính tái lập và khả năng truy vết

Để xác minh một quy trình Ant đã được cấu hình tái lập, hãy chạy hai build độc lập trên hai workspace sạch, dùng **cùng bộ đầu vào đã chốt**. Trên môi trường có Ant và JDK phù hợp, chuỗi lệnh minh họa là:

~~~bash
ant clean package
sha256sum build/dist/demo.jar
~~~

Trên PowerShell, có thể tính mã băm bằng:

~~~powershell
Get-FileHash -Path build/dist/demo.jar -Algorithm SHA256
~~~

Ghi lại SHA-256 của lần thứ nhất, xóa output, build lại ở workspace sạch thứ hai và so sánh SHA-256. Nên thử cả khi giờ thực hiện build và thư mục workspace khác nhau; nếu hai môi trường khác hệ điều hành hoặc JDK, cần xác định rõ liệu đó có phải là phạm vi tính tái lập mà dự án cam kết hay không.

| Kết quả | Cách diễn giải |
|---|---|
| Hai JAR cùng SHA-256, source và toolchain giống nhau | Có bằng chứng thực nghiệm cho tính tái lập ở bộ điều kiện đã thử |
| Hai JAR khác SHA-256 nhưng class Java giống nhau | Kiểm tra manifest, entry timestamps, tài nguyên sinh, thứ tự entry, metadata nén |
| Hai JAR khác class bytecode | Kiểm tra JDK/compiler, classpath, annotation processor, code generation, encoding, cấu hình và đầu vào |
| Một JAR được công bố hai lần, release metadata có hai thời điểm khác nhau | Bình thường nếu registry lưu các sự kiện riêng; SHA-256 của artifact vẫn có thể giống nhau |

**Đừng dùng việc tên file giống nhau hoặc chương trình chạy giống nhau để kết luận tái lập byte-for-byte.** Hai archive có thể chạy giống nhau nhưng khác timestamp hoặc manifest. Ngược lại, hai release record có thể khác publishedAt dù trỏ đến cùng một artifact.

### Những nguồn sai khác thường bị bỏ sót

- **Dependency động:** lấy “latest” hoặc bản SNAPSHOT thay đổi làm đầu vào thực tế không còn giống nhau. Cần khóa phiên bản và lý tưởng là checksum của dependency.
- **Đầu ra sinh lúc build:** file Java, JSON, tài nguyên hoặc manifest chứa thời gian hiện tại, UUID ngẫu nhiên, đường dẫn máy chủ hay số job CI.
- **Archive metadata:** thời gian sửa đổi của entry, quyền file, encoding tên file, thứ tự đóng gói, metadata do tool khác nhau ghi.
- **Môi trường biên dịch:** phiên bản JDK/Ant, compiler flags, locale, timezone, ký tự xuống dòng hoặc annotation processor không ổn định.
- **Đóng gói nhiều lần:** unpack/repack, cập nhật trực tiếp một JAR đã phát hành hoặc ký lại JAR có thể tạo byte mới. Với chữ ký số có timestamp, hãy xác định rõ đang kiểm chứng **JAR chưa ký**, **JAR đã ký**, hay **chữ ký tách rời**; không trộn các đối tượng vào cùng một phép so sánh.

Trong vận hành, nên bảo quản checksum và build provenance (nguồn, toolchain, dependency, tham số build) cùng artifact. Metadata có thể được ký hoặc kiểm chứng để ngăn gắn một release record giả với tệp khác. Cần phân biệt phép kiểm tra “hai build cho cùng byte” với kiểm tra “artifact đến từ quy trình và nguồn đáng tin cậy”: hai mục tiêu bổ trợ nhau nhưng không tương đương.

## 7. Tình huống áp dụng và lựa chọn phù hợp

**Tình huống A — Cùng mã nguồn, hai giờ build khác nhau.** Cả hai build dùng cùng revision, cùng file release-inputs.properties và cùng toolchain. Nếu artifact tái lập đúng, SHA-256 trùng nhau; log của CI vẫn ghi các giờ chạy khác nhau. Đây là kết quả mong muốn.

**Tình huống B — Phát hành lại một artifact sang môi trường production.** Bản JAR đã được kiểm chứng ở staging được promote sang production. Không sửa manifest để thêm ngày production; lưu deployedAt và release ID trong hệ thống triển khai, tham chiếu cùng checksum.

**Tình huống C — Cần truy vấn ngày khách hàng nhận bản cập nhật.** Dùng thời gian từ release registry hoặc deployment record gắn với khách hàng/kênh phân phối. Timestamp trong JAR, kể cả đã chuẩn hóa, không thể trả lời chính xác một sự kiện phân phối xảy ra sau thời điểm build.

**Tình huống D — Đổi version hoặc commit.** Đây là thay đổi đầu vào có chủ đích. JAR mới có thể mang version/revision mới và mã băm mới. Tính tái lập yêu cầu build lại **cùng bộ đầu vào** cho cùng byte; nó không yêu cầu hai phiên bản sản phẩm phải có cùng mã băm.

## 8. Nguyên tắc cần ghi nhớ

Build tái lập hướng đến mối quan hệ **đầu vào xác định → artifact có thể tái tạo và kiểm chứng bằng byte**. Phát hành hướng đến mối quan hệ **artifact đã kiểm chứng → sự kiện công bố hoặc triển khai có dấu thời gian thực**. Trong Apache Ant, có thể thực hiện sự phân tách này bằng cách chốt version/revision, chuẩn hóa timestamp archive qua **jar/zip modificationtime**, kiểm soát môi trường biên dịch và quản lý thông tin releasedAt/deployedAt trong hệ thống release bên ngoài artifact.

Không nên hy sinh thông tin kiểm toán chỉ để có SHA-256 ổn định; cũng không nên đưa thông tin kiểm toán vốn biến thiên vào JAR rồi làm mất tính tái lập. Hai nhu cầu hoàn toàn có thể cùng tồn tại khi chúng được gắn vào **đúng đối tượng dữ liệu**.

### Tài liệu tham khảo

- Apache Ant Manual — [TStamp Task](https://ant.apache.org/manual/Tasks/tstamp.html): thuộc tính thời gian, ant.tstamp.now, SOURCE_DATE_EPOCH.
- Apache Ant Manual — [Jar Task](https://ant.apache.org/manual/Tasks/jar.html): đóng gói JAR, manifest, modificationtime.
- Apache Ant Manual — [Zip Task](https://ant.apache.org/manual/Tasks/zip.html): timestamp, encoding, duplicate entries, ZIP metadata.
- [SOURCE_DATE_EPOCH specification](https://reproducible-builds.org/specs/source-date-epoch/): quy ước thời điểm nguồn phục vụ build tái lập.
