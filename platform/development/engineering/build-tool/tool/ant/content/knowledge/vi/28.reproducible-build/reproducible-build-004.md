# Quản lý timestamp, thứ tự phần tử và metadata trong kho nén với Apache Ant

## 1. Vì sao kho nén là một phần quan trọng của build tái lập?

Một bản build được gọi là **tái lập (reproducible build)** khi cùng mã nguồn, cùng dữ liệu đầu vào và cùng cấu hình công cụ tạo ra **chính xác cùng một chuỗi byte** ở đầu ra. Với Apache Ant, việc biên dịch thành công và các tệp bên trong có nội dung giống nhau chưa đủ để khẳng định hai tệp `.zip`, `.jar`, `.war`, `.ear` hoặc `.tar` giống nhau.

Giả sử hai lần chạy đều đóng gói:

```text
release.zip
├── README.md
├── config/app.properties
└── lib/core.jar
```

Nội dung ba tệp không đổi nhưng giá trị SHA-256 của `release.zip` vẫn có thể khác nhau. Nguyên nhân thường nằm trong **metadata của từng phần tử (archive entry)** hoặc cách tạo luồng byte của kho nén:

| Nguồn sai khác | Biểu hiện điển hình | Hướng kiểm soát |
| --- | --- | --- |
| Thời gian sửa đổi (mtime) | Cùng nội dung nhưng thời gian lưu trong ZIP/JAR thay đổi | Đặt một thời điểm cố định cho các entry |
| Thứ tự entry | Danh sách tệp giống nhau nhưng vị trí trong ZIP/TAR khác | Sắp xếp đầu vào theo quy tắc xác định |
| Đường dẫn và tên entry | Có lúc dùng `./config/a.txt`, lúc dùng `config/a.txt` | Chuẩn hóa đường dẫn tương đối và tiền tố |
| Entry trùng tên | Hai `fileset` cùng tạo `config/app.properties` | Phát hiện và từ chối trùng lặp |
| Quyền truy cập | Unix mode `0644`/`0755` khác nhau | Khai báo quyền cho `zipfileset`/`tarfileset` |
| Người dùng và nhóm | Header TAR ghi UID/GID hoặc tên người dùng khác | Cố định UID, GID, username và group |
| Metadata đặc thù | JAR manifest, ZIP comment, extra fields, Zip64 | Sinh metadata từ cấu hình tĩnh |
| Bộ công cụ nén | Phiên bản Ant/JDK, mức nén hoặc cách ghi header khác | Cố định phiên bản và tham số nén |

Điểm cần phân biệt:

- **Giống nội dung sau giải nén** nghĩa là các tệp tải ra giống nhau.
- **Giống byte của kho nén** nghĩa là toàn bộ header, metadata, thứ tự entry, dữ liệu nén và phần kết thúc đều giống nhau.
- **Build tái lập** đòi hỏi điều thứ hai nếu kho nén là hiện vật phát hành cần so sánh bằng checksum, chữ ký hoặc truy vết chuỗi cung ứng phần mềm.

Phần dưới tập trung vào các task và resource collection sẵn có trong Ant, rồi kết hợp chúng thành một cấu hình đóng gói có thể kiểm chứng.

## 2. Timestamp: giá trị lưu trong kho nén khác thời gian của tệp trên đĩa

### 2.1. ZIP/JAR lưu thời gian theo độ phân giải hai giây

`<zip>` và `<jar>` dùng định dạng ZIP; JAR thực chất là một biến thể ZIP có quy tắc riêng về manifest. Phần timestamp kiểu DOS trong ZIP có độ phân giải **2 giây**. Ví dụ, thời gian nguồn ở giây lẻ có thể bị làm tròn khi lưu vào kho nén.

Ant có thuộc tính `roundup` cho họ task ZIP:

| Thiết lập | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `roundup="true"` (mặc định) | Làm tròn thời gian lên mốc chẵn hai giây kế tiếp | Giúp tránh một số lần đóng gói lại không cần thiết do kiểm tra mtime |
| `roundup="false"` | Làm tròn xuống mốc chẵn hai giây | Nếu vẫn dùng mtime nguồn để quyết định cập nhật, archive có thể bị xem là cũ ở lần chạy kế tiếp |

`roundup` **không tự biến timestamp ngẫu nhiên thành timestamp cố định**. Nó chỉ quyết định chiều làm tròn. Nếu muốn byte đầu ra ổn định, cần xác định giá trị thời gian được ghi cho mọi entry.

Ngoài độ phân giải, còn có vấn đề **múi giờ**. Một số trình tạo/giải nén ZIP diễn giải thời gian theo múi giờ địa phương, trong khi công cụ khác áp dụng chuyển đổi múi giờ. Vì vậy hai máy có cùng thời điểm UTC nhưng khác cấu hình múi giờ vẫn có thể sinh hoặc hiển thị metadata khác nhau. Khi kiểm tra tính tái lập giữa các máy, hãy thống nhất múi giờ của quá trình Java/Ant, thường là UTC.

### 2.2. Cách ưu tiên từ Ant 1.10.2: `modificationtime`

Từ **Apache Ant 1.10.2**, họ task ZIP hỗ trợ `modificationtime` để gán **cùng một thời gian sửa đổi cho các entry được ghi**. Giá trị có thể là:

- Số mili giây tính từ mốc Unix epoch `1970-01-01T00:00:00Z`.
- Chuỗi thời gian ISO 8601, nên có phần múi giờ rõ ràng như `Z`.

Ví dụ đơn giản:

```xml
<zip destfile="build/release.zip"
     basedir="payload"
     modificationtime="2024-01-01T00:00:00Z"
     roundup="false"
     update="false"/>
```

Ở ví dụ này, mọi entry mới được ghi có cùng mtime đã chọn. Thời điểm `2024-01-01T00:00:00Z` nằm trên ranh giới chẵn hai giây nên không bị ảnh hưởng bởi hướng làm tròn. Nên chọn một giá trị hợp lệ với định dạng ZIP truyền thống (tránh mốc trước năm 1980), có ý nghĩa cho quy trình phát hành và luôn được truyền nhất quán.

Một quy ước thường gặp trong hệ sinh thái build tái lập là `SOURCE_DATE_EPOCH`, biểu diễn một thời điểm phát hành bằng **giây** tính từ Unix epoch. Cần chú ý: khi truyền vào `modificationtime` dưới dạng số, Ant yêu cầu **mili giây**; phải nhân giá trị giây với 1.000. Không được chép nguyên số giây thành `modificationtime` dạng số, vì thời gian nhận được sẽ gần năm 1970.

Sử dụng thời điểm cố định cho metadata **không có nghĩa** bỏ thông tin phiên bản phát hành. Phiên bản nên được lưu trong tên artifact, manifest hoặc tệp metadata được tạo từ dữ liệu đã xác định, thay vì mặc nhiên dùng đồng hồ của máy đang build.

### 2.3. Trường hợp Ant cũ: chuẩn hóa mtime trên bản sao để đóng gói

Nếu phiên bản Ant không có `modificationtime`, có thể tạo một thư mục staging, sao chép tệp vào đó và dùng `<touch>` đặt mtime trước khi đóng gói:

```xml
<target name="stage-legacy">
    <delete dir="build/stage" quiet="true"/>
    <mkdir dir="build/stage"/>

    <copy todir="build/stage">
        <fileset dir="payload"/>
    </copy>

    <!-- 2024-01-01T00:00:00Z, tính bằng mili giây -->
    <touch millis="1704067200000">
        <fileset dir="build/stage"/>
    </touch>
</target>

<target name="zip-legacy" depends="stage-legacy">
    <delete file="build/release.zip" quiet="true"/>
    <zip destfile="build/release.zip"
         basedir="build/stage"
         roundup="false"
         update="false"
         duplicate="fail"/>
</target>
```

Thao tác trên bản sao giúp tránh thay đổi mtime của tệp nguồn mà hệ thống kiểm tra phụ thuộc hoặc IDE có thể đang dùng. `<touch>` phụ thuộc vào khả năng lưu mtime của hệ thống tệp; cần giữ cùng múi giờ và kiểm tra độ chính xác thời gian khi triển khai trên nhiều hệ điều hành. Cách này cũng chỉ giải quyết timestamp, chưa giải quyết hoàn toàn thứ tự entry và metadata khác.

### 2.4. Timestamp của entry không phải timestamp của chính tệp ZIP

Hệ điều hành còn lưu mtime cho **tệp `release.zip` ở bên ngoài**. Giá trị này thường là thời điểm Ant vừa ghi tệp. Hai bản ZIP có thể có SHA-256 giống nhau dù mtime của chính tệp ZIP trên đĩa khác nhau. Khi xét tính tái lập, cần so sánh **nội dung byte của artifact** và metadata **bên trong** nó; không nên kết luận chỉ từ cột “Date modified” của tệp đầu ra.

## 3. Kiểm soát thứ tự phần tử trong archive

### 3.1. Cùng tập tệp vẫn có thể khác thứ tự

ZIP và TAR lưu các entry theo một thứ tự trong luồng byte. Ví dụ hai kho nén đều chứa ba tên sau:

```text
config/app.properties
lib/core.jar
README.md
```

Nhưng nếu thứ tự thực tế là `README.md → lib/core.jar → config/app.properties` ở lần một và `config/app.properties → README.md → lib/core.jar` ở lần hai, toàn bộ artifact có thể có hash khác dù giải nén ra cùng nội dung.

Thứ tự nhận tệp có thể phụ thuộc vào resource collection, trình quét thư mục, thứ tự khai báo các `fileset` hoặc cách trộn archive có sẵn. Không nên dựa vào thứ tự tình cờ của hệ thống tệp nếu mục tiêu là tính tái lập byte.

### 3.2. Dùng `<sort>` với bộ so sánh `name`

Ant hỗ trợ `<sort>` cho resource collection và bộ so sánh theo tên từ namespace `org.apache.tools.ant.types.resources.comparators`. Task `<zip>` chấp nhận resource collection lồng bên trong.

```xml
<zip destfile="build/release.zip"
     modificationtime="2024-01-01T00:00:00Z"
     duplicate="fail">
    <sort xmlns:rcmp="antlib:org.apache.tools.ant.types.resources.comparators">
        <fileset dir="payload" includes="**/*"/>
        <rcmp:name/>
    </sort>
</zip>
```

`<sort>` giúp sắp tài nguyên theo tên thay vì phụ thuộc thứ tự trả về của nguồn. Duy trì cách viết đường dẫn tương đối thống nhất, vì tên được dùng để sắp xếp có thể thay đổi nếu đổi `basedir`, `prefix` hoặc cách ánh xạ đường dẫn. Nếu cần một danh sách nhỏ có thứ tự nghiệp vụ cố định, `<filelist>` cũng là lựa chọn để khai báo thứ tự rõ ràng.

Với các bước gộp nhiều ZIP/JAR, cần lưu ý thứ tự của **archive đầu vào** và thứ tự **entry bên trong từng archive**. Chỉ sắp tên các tệp `*.zip` ở ngoài không đồng nghĩa các entry được giải nén/gộp bên trong đã được chuẩn hóa.

### 3.3. Chuẩn hóa tên và phạm vi đầu vào

Một bản đóng gói dễ tái lập thường có:

1. Một thư mục gốc đầu vào xác định, chẳng hạn `payload/`, để entry dùng đường dẫn tương đối.
2. Các quy tắc `includes`/`excludes` rõ ràng, tránh vô tình lấy tệp tạm, file log, dữ liệu IDE hoặc artifact của lần chạy trước.
3. Tên entry dùng đường dẫn kiểu ZIP với dấu `/`, không chứa đường dẫn tuyệt đối hoặc thông tin riêng của máy build.
4. Chính sách xử lý entry trùng tên rõ ràng.

Ví dụ:

```xml
<zip destfile="build/release.zip" duplicate="fail">
    <sort xmlns:rcmp="antlib:org.apache.tools.ant.types.resources.comparators">
        <fileset dir="payload"
                 includes="**/*"
                 excludes="**/*.tmp,**/*.log,**/.DS_Store"
                 followsymlinks="false"/>
        <rcmp:name/>
    </sort>
</zip>
```

`followsymlinks="false"` giúp tránh vô tình quét qua đường dẫn liên kết trong `fileset`. Nếu sản phẩm thực sự cần symbolic link, phải thiết kế cách đóng gói và kiểm tra riêng: hỗ trợ liên kết trong ZIP không giống TAR và phụ thuộc công cụ tiêu thụ.

**Trùng tên entry:** với `<zip>` và `<jar>`, giá trị mặc định của `duplicate` là `add`, tức có thể giữ nhiều entry cùng một đường dẫn. Hai công cụ đọc ZIP khác nhau có thể xử lý các bản trùng tên khác nhau. Khi xây artifact phát hành, `duplicate="fail"` thường là lựa chọn an toàn hơn `preserve` (giữ bản đầu) hoặc `add` (thêm tất cả).

## 4. Chuẩn hóa metadata ngoài timestamp

### 4.1. Các định dạng lưu những gì?

| Định dạng | Metadata đáng chú ý | Cách xử lý trong Ant |
| --- | --- | --- |
| ZIP | Entry name, mtime, phương pháp nén, quyền Unix (nếu ghi), comment, extra fields, Zip64 | `<zip>`, `<zipfileset>` và thuộc tính của ZIP task |
| JAR | Metadata ZIP và `META-INF/MANIFEST.MF`; có thể thêm service descriptors, index | `<jar>` kế thừa phần lớn khả năng ZIP; quản lý manifest |
| WAR/EAR | Metadata ZIP/JAR và cấu trúc ứng dụng, descriptor, thư viện | `<war>`/`<ear>`; kiểm soát cây đóng gói và metadata tương tự |
| TAR | Mtime, tên, quyền, UID/GID, username/group, loại entry, định dạng header | `<tar>` và `<tarfileset>` |
| TAR.GZ | Mọi yếu tố của TAR cộng với cách ghi luồng gzip | Chuẩn hóa TAR trước; cố định cách nén và phiên bản công cụ |

**Lưu ý về quyền:** `basedir`/`fileset` thông thường không đảm bảo mang quyền Unix trên hệ điều hành nguồn vào ZIP theo cách mong muốn. Với các file cần bit thực thi, khai báo mode rõ ràng bằng `<zipfileset>` hoặc `<tarfileset>`.

### 4.2. Khai báo quyền tường minh cho ZIP

```xml
<zip destfile="build/app.zip"
     modificationtime="2024-01-01T00:00:00Z"
     duplicate="fail"
     encoding="UTF8">
    <zipfileset dir="payload/bin"
                prefix="bin"
                includes="**/*"
                filemode="755"
                dirmode="755"/>
    <zipfileset dir="payload/config"
                prefix="config"
                includes="**/*"
                filemode="644"
                dirmode="755"/>
</zip>
```

Ở đây các file thực thi trong `bin/` có mode `755`, file cấu hình trong `config/` có mode `644`, còn thư mục được gán `755`. `filemode` và `dirmode` là chuỗi bát phân **ba chữ số**. Đảm bảo các nguồn không chồng nhau tạo ra cùng tên entry; ví dụ trên minh họa quyền và tiền tố, còn bản build hoàn chỉnh vẫn cần thống nhất thứ tự entry, input và điều kiện rebuild.

Nếu không có yêu cầu giữ thư mục rỗng hay metadata của thư mục, `filesonly="true"` trên `<zip>` có thể loại bỏ các directory entry và giảm nguồn biến động. Ngược lại, không dùng lựa chọn đó nếu directory entry hoặc thư mục rỗng là một phần của sản phẩm.

### 4.3. Metadata ảnh hưởng đến byte khác

- **Encoding của tên entry:** Với ZIP chứa tên tiếng Việt hoặc ký tự ngoài ASCII, đặt `encoding="UTF8"` và giữ nhất quán cờ UTF-8. Sự khác nhau của encoding hoặc Unicode extra fields có thể làm đổi byte archive ngay cả khi tên được hiển thị giống nhau.
- **Comment:** Nếu dùng thuộc tính `comment` của ZIP, nội dung phải cố định, không gắn thời gian, tên máy hay người build.
- **Nén:** Giữ cùng `compress`, `level`, `keepcompression` và phiên bản Ant/JDK. Dữ liệu đầu vào giống nhau không bảo đảm luồng nén giống nhau giữa mọi phiên bản thư viện.
- **Zip64:** `zip64Mode` ảnh hưởng đến các header mở rộng. Giá trị `never` chỉ phù hợp khi chắc chắn archive nằm trong giới hạn ZIP cổ điển; `as-needed` an toàn hơn khi cần lưu archive lớn nhưng cũng cần cấu hình nhất quán.
- **Gộp archive:** `<zipfileset src="...">` hoặc `<zipgroupfileset>` có thể mang theo metadata của entry nguồn. Cần kiểm soát chính các archive đầu vào và chính sách quyền, nén, trùng tên.
- **JAR manifest:** Tránh ghi `Build-Time`, tên người build, thư mục checkout, mã commit chưa cố định hoặc giá trị đồng hồ hiện tại. Thứ tự, cách xuống dòng và nội dung manifest ảnh hưởng đến byte JAR. `<jar>` có thể tạo manifest mặc định, vì vậy hãy cố định Ant/JDK khi cần so sánh qua máy.

## 5. Ví dụ hoàn chỉnh: tạo ZIP có đầu vào và metadata ổn định

Giả sử dự án có cấu trúc:

```text
demo/
├── build.xml
└── payload/
    ├── README.txt
    ├── config/
    │   └── app.properties
    └── data/
        └── sample.csv
```

Mục tiêu là tạo `build/output/release.zip`; cùng nội dung của `payload/` sẽ cho cùng byte đầu ra khi chạy trong môi trường Ant/JDK đã được cố định. Ví dụ sử dụng **Ant 1.10.2 trở lên**.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="reproducible-zip" default="dist" basedir=".">
    <property name="payload.dir" location="payload"/>
    <property name="output.dir" location="build/output"/>
    <property name="archive.mtime" value="2024-01-01T00:00:00Z"/>

    <target name="dist">
        <mkdir dir="${output.dir}"/>

        <!-- Buộc ghi lại artifact mỗi lần để tránh quyết định incremental
             dựa trên mtime cũ của file ZIP. -->
        <delete file="${output.dir}/release.zip" quiet="true"/>

        <zip destfile="${output.dir}/release.zip"
             modificationtime="${archive.mtime}"
             roundup="false"
             update="false"
             filesonly="true"
             duplicate="fail"
             whenempty="fail"
             encoding="UTF8"
             useLanguageEncodingFlag="true"
             createUnicodeExtraFields="never"
             level="6"
             zip64Mode="never">

            <sort xmlns:rcmp="antlib:org.apache.tools.ant.types.resources.comparators">
                <fileset dir="${payload.dir}"
                         includes="**/*"
                         excludes="**/*.tmp,**/*.log,**/.DS_Store"
                         followsymlinks="false"/>
                <rcmp:name/>
            </sort>
        </zip>
    </target>
</project>
```

Chạy tại thư mục chứa `build.xml`:

```bash
ant -version
ant dist
```

Những điểm có chủ đích trong cấu hình:

1. `payload.dir` cố định thư mục gốc; `output.dir` nằm ngoài `payload` nên artifact không tự bị đóng gói vào chính nó.
2. `modificationtime` cố định timestamp nội bộ; `roundup="false"` đi cùng một mốc chẵn hai giây.
3. `<sort>` cùng `<rcmp:name/>` sắp tài nguyên theo tên.
4. `duplicate="fail"` báo lỗi sớm nếu có entry trùng đường dẫn.
5. `filesonly="true"` bỏ các entry thư mục khi sản phẩm không cần chúng; đổi chính sách này nếu phải lưu thư mục rỗng.
6. `encoding="UTF8"` và các lựa chọn Unicode làm rõ quy ước tên entry.
7. `level="6"` cố định mức nén; `zip64Mode="never"` chỉ áp dụng cho ví dụ dữ liệu nhỏ. Với gói lớn, chọn chính sách Zip64 phù hợp và nhất quán.
8. `<delete>` trước `<zip>` buộc tái tạo artifact. Nếu không, kiểm tra “đầu ra đã mới hơn đầu vào” có thể khiến Ant bỏ qua việc ghi lại, che giấu thay đổi cấu hình metadata.

Nếu cần bảo toàn quyền thực thi, có thể thay cách chọn đầu vào bằng các `zipfileset` được chỉ định `filemode`. Khi đó phải xét lại cả thứ tự entry và metadata thư mục; đừng áp dụng `filesonly="true"` nếu cấu trúc cần entry thư mục.

## 6. Áp dụng cho JAR, WAR và EAR

`<jar>` kế thừa cơ chế ZIP nên cũng hỗ trợ `modificationtime` (từ Ant 1.10.2) và các thuộc tính liên quan. Với JAR, ngoài các tệp `.class` còn phải quản lý `META-INF/MANIFEST.MF`.

Ví dụ minh họa:

```xml
<target name="package-jar">
    <mkdir dir="build/libs"/>
    <delete file="build/libs/demo.jar" quiet="true"/>

    <jar destfile="build/libs/demo.jar"
         modificationtime="2024-01-01T00:00:00Z"
         roundup="false"
         duplicate="fail"
         update="false"
         index="false"
         encoding="UTF8">
        <manifest>
            <attribute name="Main-Class" value="demo.Main"/>
            <attribute name="Implementation-Version" value="1.0.0"/>
        </manifest>
        <sort xmlns:rcmp="antlib:org.apache.tools.ant.types.resources.comparators">
            <fileset dir="build/classes" includes="**/*.class"/>
            <rcmp:name/>
        </sort>
    </jar>
</target>
```

Giả định `build/classes` đã được tạo từ bước biên dịch có đầu vào ổn định. Nếu các byte `.class` khác do JDK, bộ biên dịch, thứ tự classpath hoặc mã nguồn sinh, chuẩn hóa ZIP cũng không thể làm JAR giống nhau. `Implementation-Version` phải đến từ một giá trị phát hành cố định. Giữ cùng phiên bản Ant/JDK vì manifest mặc định hoặc metadata do tool tạo có thể thay đổi giữa các phiên bản.

Đối với `<war>` và `<ear>`, nguyên tắc tương tự: cố định timestamp và thứ tự các thành phần, descriptor, dependency, manifest, quyền, cấu hình encoding. Lưu ý cấu trúc riêng như `WEB-INF/` hoặc `META-INF/application.xml` phải được bảo toàn; không nên tùy ý loại entry thư mục hoặc thay đường dẫn chỉ để đạt hash giống nhau.

## 7. TAR: metadata của người sở hữu và quyền truy cập cần được xử lý riêng

TAR có thể chứa tên người dùng, nhóm, UID/GID và mode, ngoài mtime. Với Ant, `<tarfileset>` cho phép khai báo những giá trị này:

```xml
<tar destfile="build/output/release.tar"
     longfile="posix"
     compression="none">
    <tarfileset dir="build/stage"
                prefix="release"
                username="root"
                group="root"
                uid="0"
                gid="0"
                filemode="644"
                dirmode="755"/>
</tar>
```

Ví dụ giả định `build/stage` là thư mục staging mà mtime đã được chuẩn hóa trước. `username` khác `uid` và `group` khác `gid`: nên khai báo cả hai cặp nếu cần metadata nhất quán. Những tệp phải thực thi cần một `tarfileset` riêng dùng `filemode="755"`, đồng thời loại chúng khỏi nhóm `644` để không xuất hiện hai lần.

Khác với họ task ZIP, `<tar>` không có thuộc tính `modificationtime` tương ứng trong tài liệu task. Một cách thực tế là sao chép vào staging rồi `<touch>` trước khi tạo TAR. `longfile="posix"` chọn cơ chế PAX cho tên đường dẫn dài; hãy thống nhất lựa chọn này giữa các lần build. Nếu tạo `.tar.gz`, cần xét thêm phần metadata/cách nén của luồng gzip.

Đặc biệt, Ant `<tar>` có thể đưa cùng tên entry vào nhiều lần nếu các resource collection chồng nhau. Việc khai báo quyền cho từng nhóm không tự đảm bảo tên duy nhất; hãy thiết kế các nhóm loại trừ nhau và kiểm tra thứ tự entry của TAR đầu ra.

## 8. Kiểm chứng khả năng tái lập bằng checksum và metadata

Giả sử đã lưu ví dụ `build.xml` ở mục 5 và đã có thư mục `payload/`. Chạy đóng gói hai lần, lấy hash ngay sau mỗi lần:

**Trên Linux/macOS:**

```bash
ant dist
sha256sum build/output/release.zip

ant dist
sha256sum build/output/release.zip
```

Trên macOS, nếu không có `sha256sum`, có thể dùng `shasum -a 256 build/output/release.zip`.

**Trên PowerShell (Windows):**

```powershell
ant dist
Get-FileHash -Algorithm SHA256 build/output/release.zip

ant dist
Get-FileHash -Algorithm SHA256 build/output/release.zip
```

Hai giá trị hash cần giống nhau. Muốn kiểm tra mạnh hơn, xây từ **hai thư mục checkout sạch riêng biệt** nhưng cùng revision, cùng phiên bản Ant/JDK và cùng dữ liệu đầu vào; sau đó so sánh hash. Chạy lại hai lần trên cùng một thư mục chưa đủ để phát hiện phụ thuộc vào đường dẫn checkout hay dữ liệu còn sót từ build cũ.

Có thể liệt kê entry bằng các công cụ thông dụng:

```bash
# Danh sách theo thứ tự xuất hiện trong ZIP
unzip -Z -1 build/output/release.zip

# Thông tin về thời gian, method và kích thước (tùy bản unzip)
unzip -l build/output/release.zip

# Với JAR
jar tf build/libs/demo.jar

# Với TAR
tar -tvf build/output/release.tar
```

Các lệnh trên chủ yếu giúp quan sát; chúng không thay thế so sánh byte. Nếu hash khác, dùng công cụ hỗ trợ phân tích nhị phân như `zipinfo -v` hoặc `diffoscope`, khi có sẵn, để xác định khác biệt nằm ở timestamp, thứ tự entry, extra field, manifest hay dữ liệu nén.

### Bảng khoanh vùng nguyên nhân

| Triệu chứng | Nguyên nhân cần xem trước | Cách khắc phục |
| --- | --- | --- |
| Hash thay đổi mỗi lần build, nội dung giải nén không đổi | Entry mtime gắn đồng hồ hiện tại; metadata sinh động | Dùng `modificationtime`, bỏ timestamp động trong manifest |
| Hash khác giữa máy A và B | Múi giờ, phiên bản Ant/JDK, encoding, kiểu nén | Giữ môi trường build nhất quán; kiểm tra từng entry |
| Danh sách entry giống nhưng thứ tự khác | Thứ tự nguồn hoặc gộp nhiều fileset/archive | Dùng `<sort>` theo tên; kiểm soát thứ tự nguồn gộp |
| Script mất quyền thực thi | Chỉ dùng `fileset` thông thường hoặc unzip không khôi phục mode | Khai báo `zipfileset filemode`/`tarfileset filemode`; kiểm tra trình giải nén |
| Ant không tạo lại archive sau khi đổi cấu hình | Kiểm tra mtime incremental cho rằng artifact còn mới | Xóa artifact trước khi đóng gói hoặc thiết kế lại dependency |
| Có hai entry cùng tên | Các nguồn chồng nhau; chính sách `duplicate="add"` mặc định của ZIP | Đặt `duplicate="fail"` và loại chồng lặp |
| TAR khác dù mtime đã giống | UID/GID, user/group, mode, thứ tự, long-file header | Cố định trường của `tarfileset` và định dạng TAR |
| ZIP khác chỉ khi gói lớn | Cách dùng Zip64/extra fields | Cố định `zip64Mode` theo nhu cầu và phiên bản công cụ |

## 9. Những giới hạn cần hiểu

**Kiểm soát metadata archive là điều kiện cần, chưa phải toàn bộ build tái lập.** Mọi byte của các tệp đầu vào vẫn phải ổn định. Ví dụ: biên dịch Java có thể phụ thuộc vào phiên bản JDK; tệp cấu hình có thể chứa đường dẫn tuyệt đối; bộ sinh mã có thể ghi thời gian hiện tại; dependency được tải không cố định phiên bản; line ending có thể khác giữa Windows và Linux.

Cũng không nên nhầm `update="false"` với “luôn tạo mới”. Theo cơ chế incremental của Ant, một artifact đã tồn tại có thể được xem là còn mới; vì vậy ví dụ đóng gói tái lập xóa artifact trước khi tạo. Thời gian của entry ZIP có độ phân giải hai giây còn làm các phép so sánh mtime trở nên nhạy cảm hơn.

Với mục tiêu so sánh byte **trên nhiều máy**, một quy trình đáng tin cậy cần thống nhất đồng thời:

1. **Đầu vào:** cùng revision, dependencies và file sinh ra trước khi đóng gói.
2. **Nội dung archive:** cùng danh sách đường dẫn, nội dung, thứ tự và quy tắc xử lý entry trùng.
3. **Metadata archive:** cùng mtime, quyền, owner/group (với TAR), manifest, encoding, extra fields và chính sách Zip64.
4. **Công cụ:** cùng phiên bản Ant, JDK, thư viện nén, tùy chọn nén và múi giờ.
5. **Quy trình:** đóng gói từ trạng thái sạch, rồi so sánh checksum của artifact.

## 10. Bài thực hành tự kiểm tra

1. Tạo ba file trong `payload/` như mục 5 và chạy `ant dist` hai lần. Ghi lại SHA-256.
2. Chỉ thay đổi **mtime của file nguồn** (không thay nội dung), sau đó chạy `ant dist`. Với `modificationtime` cố định và môi trường giống nhau, hash ZIP dự kiến không đổi.
3. Thêm file mới vào `payload/config/`, đóng gói lại rồi quan sát danh sách entry. Hash phải đổi vì **nội dung tập đầu vào đã đổi**.
4. Tạo hai `zipfileset` dẫn đến cùng tên entry và thử `duplicate="fail"`. Quan sát lỗi để hiểu vì sao cần phát hiện xung đột sớm.
5. Tạo một JAR có manifest ghi giờ hiện tại; so sánh hash giữa hai lần build. Thay trường này bằng giá trị cố định, đồng thời chuẩn hóa timestamp và thứ tự, rồi thử lại.

Điểm cốt lõi của bài học: với Apache Ant, hãy xem **kho nén là một cấu trúc dữ liệu có metadata và thứ tự**, chứ không chỉ là “một túi chứa file”. Một artifact tái lập được phải có cả **byte nội dung** lẫn **cách biểu diễn archive** ổn định.

## Tài liệu tham khảo

- [Apache Ant — Zip task](https://ant.apache.org/manual/Tasks/zip.html): `modificationtime`, `roundup`, `duplicate`, encoding, nén, Zip64.
- [Apache Ant — Jar task](https://ant.apache.org/manual/Tasks/jar.html): JAR manifest và các thuộc tính kế thừa từ ZIP.
- [Apache Ant — ZipFileSet](https://ant.apache.org/manual/Types/zipfileset.html): `filemode`, `dirmode`, `prefix`, `fullpath`.
- [Apache Ant — Resources](https://ant.apache.org/manual/Types/resources.html): `<sort>` và bộ so sánh `name`.
- [Apache Ant — Touch task](https://ant.apache.org/manual/Tasks/touch.html): thay đổi mtime trên file hoặc tập tài nguyên.
- [Apache Ant — Tar task](https://ant.apache.org/manual/Tasks/tar.html) và [TarFileSet](https://ant.apache.org/manual/Types/tarfileset.html): metadata người sở hữu, quyền và header TAR.
- [Reproducible Builds — Archive metadata](https://reproducible-builds.org/docs/archives/): các nguồn sai khác phổ biến ở metadata kho nén.
