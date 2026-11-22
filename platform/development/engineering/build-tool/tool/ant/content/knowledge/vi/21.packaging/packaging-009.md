# Tạo ZIP, TAR, GZip và các gói phân phối bằng Apache Ant

Apache Ant có các task để gom file và thư mục thành archive, nén dữ liệu và tạo gói phát hành. Với một dự án Java, build có thể biên dịch mã nguồn, chạy test, tập hợp JAR cùng cấu hình và script, rồi tạo các định dạng phù hợp với cách phân phối: ZIP cho Windows và môi trường đa nền tảng, TAR cho hệ Unix-like, TAR.GZ hoặc TAR.BZ2 để giảm dung lượng, và JAR cho thư viện hoặc ứng dụng Java.

Các task chính cần biết:

- `<zip>` tạo archive ZIP từ file và thư mục.
- `<tar>` tạo archive TAR, có thể kết hợp nén gzip hoặc bzip2.
- `<gzip>` và `<bzip2>` nén một file thành luồng nén riêng.
- `<jar>` tạo Java Archive, là định dạng dựa trên ZIP có quy ước dành cho Java.
- `<unzip>`, `<untar>` và `<unjar>` giải nén các định dạng tương ứng.

Để tạo gói phân phối dễ sử dụng và có thể tái tạo, cần xác định rõ file nào được đưa vào, chúng nằm ở đâu bên trong archive, metadata nào phải giữ và cách đặt tên artifact theo phiên bản.

## 1. Archive và compression là hai công việc khác nhau

Archive gom nhiều file và thư mục thành một cấu trúc có tên đường dẫn. Compression giảm kích thước dữ liệu bằng thuật toán nén.

| Định dạng | Vai trò | Đặc điểm thường gặp |
|---|---|---|
| ZIP | Archive có thể chứa nhiều file và thư mục | Dễ trao đổi trên Windows, Linux và macOS; hỗ trợ nén từng entry |
| TAR | Archive gom nhiều file thành một luồng | Phổ biến trên Unix-like; bản thân TAR không nén |
| GZip (.gz) | Nén một luồng/file | Thường dùng nén file TAR thành .tar.gz |
| BZip2 (.bz2) | Nén một luồng/file | Thường dùng nén file TAR thành .tar.bz2 |
| JAR | Archive theo quy ước Java | Dựa trên ZIP và có thể chứa manifest, class, resource |

Một file `.tar` có thể chứa cả cây thư mục nhưng không tự làm dữ liệu nhỏ hơn. Khi cần nén, có thể tạo TAR rồi nén thành GZip hoặc BZip2. ZIP thường kết hợp cả gom file và nén trong một bước.

Ví dụ về hai chuỗi thao tác tương đương:

~~~text
Nhiều file + thư mục
       |
       +----> ZIP task ----------------> application.zip
       |
       +----> TAR task ----------------> application.tar
                                         |
                                         +----> GZip task --> application.tar.gz
                                         |
                                         +----> BZip2 task -> application.tar.bz2
~~~

Không nên nhầm GZip với ZIP. GZip không phải định dạng archive đa file thông thường; nó nén một luồng dữ liệu. Muốn nén cả cây thư mục bằng GZip, thường tạo TAR trước rồi mới nén file TAR.

## 2. Chuẩn bị thư mục staging cho gói phát hành

Một quy trình đóng gói tốt thường không lấy file trực tiếp từ nhiều vị trí trong source tree ở từng task. Thay vào đó, tạo một thư mục staging có cấu trúc giống thư mục người dùng sẽ nhận được.

Ví dụ:

~~~text
inventory/
├── build.xml
├── src/
├── lib/
├── config/
├── scripts/
├── build/
│   ├── classes/
│   └── staging/
└── dist/
~~~

Sau khi biên dịch và tập hợp file, staging có thể có cấu trúc:

~~~text
build/staging/
└── inventory-1.4.0/
    ├── bin/
    │   └── inventory.sh
    ├── conf/
    │   └── application.properties
    ├── lib/
    │   ├── inventory.jar
    │   └── dependency-a.jar
    ├── README.md
    └── LICENSE
~~~

Khi archive được giải nén, người nhận có một thư mục gốc duy nhất là `inventory-1.4.0`. Cấu trúc này giúp tránh việc các file bị bung trực tiếp vào thư mục hiện tại và lẫn với dữ liệu khác.

Khai báo property dùng chung:

~~~xml
<property name="app.name" value="inventory" />
<property name="app.version" value="1.4.0" />
<property name="build.dir" location="build" />
<property name="staging.dir" location="${build.dir}/staging" />
<property name="dist.dir" location="dist" />
<property name="release.root"
          value="${app.name}-${app.version}" />
<property name="release.dir"
          location="${staging.dir}/${release.root}" />
~~~

Dùng property giúp đổi phiên bản hoặc thư mục đầu ra tại một nơi. Nếu version được truyền từ dòng lệnh, có thể dùng `-Dapp.version=...` để tạo artifact cho lần build cụ thể.

## 3. Tạo file ZIP bằng task zip

Task `<zip>` tạo archive ZIP từ một thư mục cơ sở hoặc một hay nhiều resource collection như FileSet và ZipFileSet.

### 3.1. ZIP toàn bộ thư mục staging

Cách đơn giản nhất là chỉ định basedir:

~~~xml
<target name="zip-release">
    <mkdir dir="${dist.dir}" />

    <zip destfile="${dist.dir}/${release.root}.zip"
         basedir="${staging.dir}" />
</target>
~~~

Task đưa nội dung của staging vào archive theo đường dẫn tương đối với basedir. Nếu staging chứa thư mục inventory-1.4.0, thư mục này cũng xuất hiện trong ZIP.

Có thể dùng thuộc tính includes và excludes để giới hạn file:

~~~xml
<zip destfile="${dist.dir}/${release.root}.zip"
     basedir="${staging.dir}"
     includes="**/*"
     excludes="**/*.tmp,**/*.bak,**/.DS_Store" />
~~~

Khi cần quy tắc phức tạp hơn, nested FileSet dễ đọc và có thể chứa nhiều include/exclude:

~~~xml
<zip destfile="${dist.dir}/${release.root}.zip">
    <fileset dir="${release.dir}">
        <include name="**/*" />
        <exclude name="**/*.tmp" />
        <exclude name="**/*.bak" />
        <exclude name="**/.DS_Store" />
    </fileset>
</zip>
~~~

FileSet xác định thư mục gốc để quét. Các mẫu được tính tương đối với thư mục đó. Dùng `**/*` khi muốn chọn file ở mọi cấp, sau đó loại các file không nên phát hành.

### 3.2. Sắp xếp đường dẫn bên trong ZIP bằng zipfileset

Khi các file nguồn nằm ở nhiều vị trí nhưng cần gom vào một cấu trúc thống nhất, dùng `<zipfileset>` với thuộc tính `prefix`.

~~~xml
<zip destfile="${dist.dir}/${release.root}.zip">
    <zipfileset dir="build/libs"
                prefix="${release.root}/lib">
        <include name="*.jar" />
    </zipfileset>

    <zipfileset dir="config"
                prefix="${release.root}/conf">
        <include name="*.properties" />
        <include name="*.xml" />
    </zipfileset>

    <zipfileset dir="scripts"
                prefix="${release.root}/bin">
        <include name="*.sh" />
        <include name="*.bat" />
    </zipfileset>

    <zipfileset dir="."
                prefix="${release.root}">
        <include name="README.md" />
        <include name="LICENSE" />
    </zipfileset>
</zip>
~~~

Trong ví dụ:

- Các JAR từ build/libs được đặt dưới thư mục lib.
- Cấu hình được đặt dưới conf.
- Script được đặt dưới bin.
- README và LICENSE nằm ở thư mục gốc của bản phát hành.

`prefix` thêm đường dẫn đứng trước tên tương đối của file trong archive. Nhờ vậy, cấu trúc ZIP không phụ thuộc vào việc file nguồn đang nằm ở thư mục nào trong repository.

### 3.3. Dùng fullpath cho một file có vị trí cố định

Thuộc tính `fullpath` của ZipFileSet đặt một file vào đúng một đường dẫn trong archive. Nó phù hợp khi chỉ chọn một file và muốn đổi tên hoặc vị trí:

~~~xml
<zip destfile="${dist.dir}/${release.root}.zip">
    <zipfileset dir="config"
                includes="production.properties"
                fullpath="${release.root}/conf/application.properties" />
</zip>
~~~

Không dùng fullpath cho một tập nhiều file vì tất cả file được chọn sẽ cạnh tranh cùng một đường dẫn. Với nhiều file, dùng prefix để giữ cấu trúc tương đối.

## 4. Các tùy chọn ZIP thường dùng

Task zip có một số thuộc tính kiểm soát cách tạo archive.

| Thuộc tính | Ý nghĩa |
|---|---|
| destfile | Đường dẫn archive ZIP cần tạo |
| basedir | Thư mục nguồn cơ sở |
| update | Cập nhật archive hiện có thay vì tạo lại toàn bộ |
| compress | Có nén dữ liệu của từng entry hay lưu không nén |
| level | Mức nén, thường từ 0 đến 9 |
| encoding | Encoding dùng cho tên entry trong archive |
| filesonly | Chỉ thêm file, không thêm entry thư mục |
| whenempty | Cách xử lý khi không có file để thêm |
| duplicate | Cách xử lý khi nhiều nguồn tạo entry trùng tên |
| keepcompression | Giữ phương pháp nén của entry cũ khi cập nhật, trong trường hợp áp dụng |

### 4.1. update và việc tạo archive mới

Mặc định, task zip tạo archive theo nội dung nguồn của lần chạy. Đặt `update="true"` khi muốn cập nhật archive đã tồn tại:

~~~xml
<zip destfile="${dist.dir}/${release.root}.zip"
     basedir="${release.dir}"
     update="true" />
~~~

Ở chế độ update, Ant thêm entry mới hoặc cập nhật entry cần thiết theo trạng thái file. Các entry cũ không còn trong thư mục nguồn có thể vẫn tồn tại trong archive. Vì vậy, update phù hợp với quy trình cập nhật có chủ đích, nhưng không phải lựa chọn tốt khi cần archive phản ánh chính xác toàn bộ nội dung hiện tại của staging.

Với gói phát hành cần nội dung sạch, thường nên tạo lại archive từ staging đã được chuẩn bị đầy đủ thay vì cập nhật archive cũ.

### 4.2. Mức nén và tốc độ

Thuộc tính compress điều khiển việc nén entry. Mức nén có thể đặt qua level:

~~~xml
<zip destfile="${dist.dir}/${release.root}.zip"
     basedir="${release.dir}"
     compress="true"
     level="9" />
~~~

Mức nén cao có thể giảm dung lượng nhưng tốn CPU và thời gian hơn. Với file đã nén như JAR, PNG, JPEG, MP4 hoặc ZIP khác, nén thêm thường không giảm đáng kể dung lượng. Có thể giữ mức nén mặc định hoặc chọn mức thấp hơn để tăng tốc build.

Nếu cần lưu file không nén trong ZIP, có thể dùng `compress="false"`. Điều này vẫn tạo archive ZIP nhưng lưu entry theo dạng stored.

### 4.3. Tên file trùng nhau trong archive

Nếu nhiều FileSet hoặc ZipFileSet tạo ra cùng một đường dẫn bên trong archive, cần xác định chính sách duplicate. Tùy chọn duplicate của task zip cho phép lựa chọn cách xử lý các entry trùng tên; các chế độ thường dùng gồm add, preserve hoặc fail.

Để tránh archive khó dự đoán, nên thiết kế prefix riêng cho từng nhóm nguồn và không để hai FileSet ghi vào cùng một đường dẫn trừ khi có lý do rõ ràng. Nếu cần bảo đảm không có trùng lặp, dùng chế độ fail để phát hiện lỗi cấu trúc sớm.

### 4.4. Archive rỗng

Thuộc tính whenempty kiểm soát cách xử lý khi không có tài nguyên nào được chọn. Tùy chọn có thể yêu cầu báo lỗi, bỏ qua hoặc tạo archive rỗng. Với gói phát hành, một archive rỗng thường là dấu hiệu staging sai hoặc mẫu include không khớp; hãy chọn hành vi làm lộ lỗi thay vì âm thầm xuất bản artifact không có nội dung.

## 5. Tạo TAR bằng task tar

TAR gom file và thư mục vào một archive tuần tự. Task `<tar>` nhận FileSet hoặc TarFileSet để xác định nội dung.

Ví dụ:

~~~xml
<tar destfile="${dist.dir}/${release.root}.tar">
    <tarfileset dir="${release.dir}"
                prefix="${release.root}" />
</tar>
~~~

Tất cả nội dung trong release.dir được lưu dưới thư mục gốc release.root trong archive. Khi giải nén, người nhận có cấu trúc thư mục phát hành tương ứng.

Có thể chọn file bằng include/exclude:

~~~xml
<tar destfile="${dist.dir}/${release.root}.tar">
    <tarfileset dir="${release.dir}"
                prefix="${release.root}">
        <include name="**/*" />
        <exclude name="**/*.tmp" />
        <exclude name="**/*.bak" />
        <exclude name="**/.DS_Store" />
    </tarfileset>
</tar>
~~~

TarFileSet hỗ trợ metadata phù hợp với TAR như quyền file, quyền thư mục và thông tin chủ sở hữu. Điều này quan trọng khi gói được giải nén trên Unix-like và cần giữ script có quyền thực thi.

## 6. Giữ quyền file và thư mục trong TAR

Khác với ZIP phổ biến trong trao đổi đa nền tảng, TAR thường được dùng để triển khai trên Linux/Unix, nơi quyền file có ý nghĩa trực tiếp.

TarFileSet cho phép đặt `filemode` và `dirmode`:

~~~xml
<tar destfile="${dist.dir}/${release.root}.tar">
    <tarfileset dir="${release.dir}"
                prefix="${release.root}"
                filemode="644"
                dirmode="755">
        <include name="**/*" />
        <exclude name="bin/inventory.sh" />
    </tarfileset>

    <tarfileset dir="${release.dir}"
                prefix="${release.root}"
                filemode="755">
        <include name="bin/inventory.sh" />
    </tarfileset>
</tar>
~~~

Ví dụ này đặt:

- File thông thường ở quyền 644: chủ sở hữu có quyền đọc/ghi, nhóm và người khác có quyền đọc.
- Thư mục ở quyền 755: chủ sở hữu có quyền đọc/ghi/truy cập, nhóm và người khác có quyền đọc/truy cập.
- Script inventory.sh ở quyền 755 để có thể thực thi sau khi giải nén.

Các giá trị mode thường được viết theo hệ bát phân. Hãy chọn quyền tối thiểu cần thiết. Không nên đặt mọi file thành 777 vì điều đó cho phép mọi người ghi và thực thi nội dung, làm giảm an toàn của gói phát hành.

Nếu cần lưu metadata owner/group, TarFileSet có thể nhận các thuộc tính liên quan như username, group, uid và gid. Việc người giải nén có thể khôi phục đúng owner hay không còn phụ thuộc quyền của tiến trình và công cụ giải nén trên hệ thống đích.

## 7. Xử lý tên đường dẫn dài trong TAR

Định dạng TAR truyền thống có giới hạn về cách lưu tên file và đường dẫn. Dự án có package hoặc resource nằm trong cây thư mục sâu có thể tạo đường dẫn dài hơn giới hạn của header TAR cũ.

Task tar có thuộc tính `longfile` để chọn cách xử lý tên dài. Các chế độ thường gặp:

| Chế độ | Hành vi |
|---|---|
| warn | Cảnh báo khi gặp tên dài và dùng cách xử lý tương thích theo cấu hình |
| fail | Báo lỗi khi tên vượt giới hạn |
| truncate | Cắt ngắn tên |
| omit | Bỏ qua entry có tên không thể biểu diễn |
| gnu | Dùng phần mở rộng tên dài theo GNU TAR |
| posix | Dùng định dạng POSIX/PAX để biểu diễn tên dài |

Ví dụ dùng định dạng POSIX/PAX:

~~~xml
<tar destfile="${dist.dir}/${release.root}.tar"
     longfile="posix">
    <tarfileset dir="${release.dir}"
                prefix="${release.root}" />
</tar>
~~~

Chế độ posix phù hợp khi cần giữ nguyên đường dẫn dài và công cụ giải nén đích hỗ trợ PAX. Chế độ gnu phù hợp với hệ sinh thái GNU TAR. Nếu cần tương thích với hệ thống rất cũ, hãy kiểm tra công cụ giải nén thực tế trước khi chọn định dạng.

Không nên dùng truncate cho gói phát hành nếu tên file đầy đủ là cần thiết; hai file có tên dài khác nhau có thể bị cắt thành cùng một tên và gây xung đột.

## 8. Nén TAR bằng GZip hoặc BZip2

TAR chỉ gom file. Để giảm dung lượng, có thể nén bằng GZip hoặc BZip2.

### 8.1. Tạo TAR.GZ trực tiếp

Task tar hỗ trợ thuộc tính compression để nén archive khi tạo:

~~~xml
<tar destfile="${dist.dir}/${release.root}.tar.gz"
     compression="gzip"
     longfile="posix">
    <tarfileset dir="${release.dir}"
                prefix="${release.root}" />
</tar>
~~~

Ant tạo archive TAR và nén bằng GZip, kết quả là file `.tar.gz` (cũng thường được viết `.tgz`).

### 8.2. Tạo TAR.BZ2

Có thể chọn BZip2:

~~~xml
<tar destfile="${dist.dir}/${release.root}.tar.bz2"
     compression="bzip2"
     longfile="posix">
    <tarfileset dir="${release.dir}"
                prefix="${release.root}" />
</tar>
~~~

BZip2 thường nén tốt với một số loại dữ liệu văn bản nhưng có thể tốn thời gian và CPU hơn GZip. Hãy đo dung lượng và thời gian trên dữ liệu thật trước khi chọn.

### 8.3. Nén TAR đã tạo bằng task gzip hoặc bzip2

Một cách khác là tạo file TAR trước, sau đó gọi task nén riêng:

~~~xml
<target name="tar-then-gzip">
    <tar destfile="${dist.dir}/${release.root}.tar">
        <tarfileset dir="${release.dir}"
                    prefix="${release.root}" />
    </tar>

    <gzip src="${dist.dir}/${release.root}.tar"
          destfile="${dist.dir}/${release.root}.tar.gz" />
</target>
~~~

Tương tự với BZip2:

~~~xml
<bzip2 src="${dist.dir}/${release.root}.tar"
       destfile="${dist.dir}/${release.root}.tar.bz2" />
~~~

Dùng compression ngay trong task tar thường gọn hơn vì chỉ cần một task. Tách hai bước hữu ích khi muốn giữ lại file TAR chưa nén hoặc cần tái sử dụng nó cho nhiều định dạng.

Không nên vừa yêu cầu tar nén gzip vừa gọi gzip lần nữa trên file kết quả. Điều đó tạo nén lồng, không phải archive `.tar.gz` thông thường.

## 9. Nén một file riêng bằng GZip hoặc BZip2

Task `<gzip>` và `<bzip2>` nén một file đầu vào thành một file nén. Chúng không tự gom nhiều file từ thư mục.

Ví dụ nén một file log:

~~~xml
<gzip src="build/logs/application.log"
      destfile="dist/application.log.gz" />
~~~

Với BZip2:

~~~xml
<bzip2 src="build/reports/report.txt"
       destfile="dist/report.txt.bz2" />
~~~

Các task này phù hợp khi cần lưu trữ hoặc truyền một file lớn như log, dump dữ liệu hoặc báo cáo. Nếu cần đóng gói nhiều file cùng cấu trúc thư mục, hãy tạo ZIP hoặc TAR trước.

Thông thường, file nguồn vẫn được giữ lại sau khi nén. Nếu muốn xóa file nguồn sau khi tạo archive, hãy dùng task delete riêng sau khi chắc chắn quá trình nén thành công và file đích hợp lệ.

## 10. Tạo JAR cho ứng dụng hoặc thư viện Java

Task `<jar>` tạo Java Archive, là định dạng dựa trên ZIP với quy ước về nội dung và manifest. JAR thường chứa class đã biên dịch, resource và metadata để Java runtime hoặc công cụ khác sử dụng.

Ví dụ đóng gói lớp ứng dụng:

~~~xml
<jar destfile="${dist.dir}/inventory.jar"
     basedir="build/classes" />
~~~

Để tạo JAR có manifest chỉ định lớp chạy chính:

~~~xml
<jar destfile="${dist.dir}/inventory.jar"
     basedir="build/classes">
    <manifest>
        <attribute name="Main-Class"
                   value="com.example.inventory.Main" />
        <attribute name="Implementation-Version"
                   value="${app.version}" />
    </manifest>
</jar>
~~~

Sau khi tạo, có thể chạy ứng dụng bằng:

~~~bash
java -jar dist/inventory.jar
~~~

Nếu ứng dụng phụ thuộc các JAR ngoài, chỉ thêm chúng vào classpath khi chạy chưa đủ để lệnh `java -jar` tự tìm thấy chúng. Có thể:

- Đóng gói dependency vào một cấu trúc phân phối riêng và cung cấp script chạy với classpath.
- Tạo manifest Class-Path trỏ đến các JAR tương đối trong cùng gói.
- Dùng công cụ tạo executable/fat JAR nếu dự án cần một JAR duy nhất chứa dependency.

Ví dụ manifest Class-Path:

~~~xml
<jar destfile="${dist.dir}/inventory.jar"
     basedir="build/classes">
    <manifest>
        <attribute name="Main-Class"
                   value="com.example.inventory.Main" />
        <attribute name="Class-Path"
                   value="lib/dependency-a.jar lib/dependency-b.jar" />
    </manifest>
</jar>
~~~

Các đường dẫn trong Class-Path được phân giải tương đối với vị trí JAR. Vì vậy, khi phân phối, hãy giữ các JAR trong thư mục lib tương ứng với manifest.

## 11. Ghép nhiều archive bằng zipgroupfileset

Khi cần tạo một ZIP chứa nội dung của các ZIP/JAR khác, có thể dùng `zipgroupfileset`:

~~~xml
<zip destfile="${dist.dir}/all-libraries.zip">
    <zipgroupfileset dir="lib">
        <include name="*.zip" />
        <include name="*.jar" />
    </zipgroupfileset>
</zip>
~~~

ZipGroupFileSet lấy nội dung bên trong các archive nguồn và thêm vào archive đích. Nó khác với FileSet thông thường: FileSet chọn chính file ZIP/JAR như một file, còn ZipGroupFileSet đọc các entry bên trong archive.

Cần cẩn thận với tên entry trùng nhau khi ghép nhiều JAR. Hai thư viện có thể chứa cùng một resource hoặc file metadata. Xác định chính sách duplicate và kiểm tra archive kết quả để tránh ghi đè tài nguyên không mong muốn.

Không phải mọi JAR đều nên được hợp nhất thành một JAR. Manifest, chữ ký số, service descriptor và metadata của thư viện có thể cần xử lý riêng khi tạo fat JAR. Nếu yêu cầu đóng gói phức tạp, hãy dùng plugin hoặc công cụ chuyên biệt phù hợp thay vì chỉ ghép ZIP một cách máy móc.

## 12. Giải nén ZIP, TAR và JAR

Ant có các task giải nén tương ứng.

### 12.1. Giải nén ZIP

~~~xml
<unzip src="${dist.dir}/${release.root}.zip"
       dest="build/unpacked" />
~~~

### 12.2. Giải nén TAR

~~~xml
<untar src="${dist.dir}/${release.root}.tar"
       dest="build/unpacked" />
~~~

### 12.3. Giải nén JAR

~~~xml
<unjar src="${dist.dir}/inventory.jar"
       dest="build/jar-contents" />
~~~

Các task giải nén hữu ích trong kiểm thử gói phân phối: tạo archive, bung ra một thư mục tạm và xác nhận các file quan trọng có mặt.

Ví dụ:

~~~xml
<target name="verify-zip">
    <mkdir dir="build/verify/zip" />

    <unzip src="${dist.dir}/${release.root}.zip"
           dest="build/verify/zip" />

    <available file="build/verify/zip/${release.root}/README.md"
               type="file"
               property="zip.readme.present" />

    <fail unless="zip.readme.present"
          message="README.md is missing from the ZIP distribution." />
</target>
~~~

Khi giải nén archive không đáng tin cậy, hãy dùng thư mục đích riêng, có kiểm soát quyền ghi và không giải nén vào thư mục chứa dữ liệu quan trọng. Chỉ xử lý archive do nguồn tin cậy tạo ra trong quy trình phát hành.

## 13. Ví dụ hoàn chỉnh: tạo ZIP và TAR.GZ cho một bản phát hành

Buildfile sau tập hợp JAR, dependency, cấu hình, script, README và LICENSE vào staging, rồi tạo hai định dạng phân phối.

~~~xml
<project name="inventory" default="dist" basedir=".">
    <property name="app.name" value="inventory" />
    <property name="app.version" value="1.4.0" />

    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="staging.dir" location="${build.dir}/staging" />
    <property name="release.root"
              value="${app.name}-${app.version}" />
    <property name="release.dir"
              location="${staging.dir}/${release.root}" />
    <property name="dist.dir" location="dist" />

    <target name="clean">
        <delete dir="${build.dir}" />
        <delete dir="${dist.dir}" />
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}" />
        <javac srcdir="src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8" />
    </target>

    <target name="stage" depends="compile">
        <mkdir dir="${release.dir}/bin" />
        <mkdir dir="${release.dir}/conf" />
        <mkdir dir="${release.dir}/lib" />

        <jar destfile="${release.dir}/lib/${app.name}.jar"
             basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class"
                           value="com.example.inventory.Main" />
                <attribute name="Implementation-Version"
                           value="${app.version}" />
            </manifest>
        </jar>

        <copy todir="${release.dir}/conf">
            <fileset dir="config">
                <include name="*.properties" />
                <include name="*.xml" />
                <exclude name="local/**" />
            </fileset>
        </copy>

        <copy todir="${release.dir}/bin">
            <fileset dir="scripts">
                <include name="*.sh" />
                <include name="*.bat" />
            </fileset>
        </copy>

        <copy file="README.md" todir="${release.dir}" />
        <copy file="LICENSE" todir="${release.dir}" />

        <copy todir="${release.dir}/lib">
            <fileset dir="lib">
                <include name="*.jar" />
            </fileset>
        </copy>
    </target>

    <target name="dist" depends="stage">
        <mkdir dir="${dist.dir}" />

        <zip destfile="${dist.dir}/${release.root}.zip">
            <fileset dir="${staging.dir}">
                <include name="${release.root}/**" />
                <exclude name="**/*.tmp" />
                <exclude name="**/*.bak" />
            </fileset>
        </zip>

        <tar destfile="${dist.dir}/${release.root}.tar.gz"
             compression="gzip"
             longfile="posix">
            <tarfileset dir="${staging.dir}"
                        prefix=""
                        filemode="644"
                        dirmode="755">
                <include name="${release.root}/**" />
                <exclude name="**/*.tmp" />
                <exclude name="**/*.bak" />
                <exclude name="${release.root}/bin/*.sh" />
            </tarfileset>

            <tarfileset dir="${staging.dir}"
                        prefix=""
                        filemode="755"
                        dirmode="755">
                <include name="${release.root}/bin/*.sh" />
            </tarfileset>
        </tar>
    </target>
</project>
~~~

Chạy:

~~~bash
ant clean dist
~~~

Kết quả mong đợi:

~~~text
dist/
├── inventory-1.4.0.zip
└── inventory-1.4.0.tar.gz
~~~

ZIP giữ cấu trúc thư mục để người dùng dễ giải nén trên nhiều hệ điều hành. TAR.GZ giữ quyền thực thi của script theo metadata TAR, phù hợp hơn khi triển khai trên Linux/Unix.

Trong dự án thực tế, target stage nên bao gồm output sau khi test thành công, các dependency đúng phiên bản và file cấu hình mẫu. Không đưa cấu hình chứa mật khẩu, token, file tạm hoặc dữ liệu môi trường cá nhân vào gói phát hành.

## 14. Kiểm tra nội dung archive sau khi tạo

Một task tạo archive kết thúc thành công chưa đủ để khẳng định gói phát hành có đúng nội dung. Có thể kiểm tra bằng cách giải nén vào thư mục tạm và xác nhận các file quan trọng.

Ví dụ:

~~~xml
<target name="verify-distribution" depends="dist">
    <mkdir dir="build/verify/zip" />
    <mkdir dir="build/verify/tar" />

    <unzip src="${dist.dir}/${release.root}.zip"
           dest="build/verify/zip" />

    <untar src="${dist.dir}/${release.root}.tar.gz"
           dest="build/verify/tar" />

    <available file="build/verify/zip/${release.root}/README.md"
               type="file"
               property="zip.readme.ok" />

    <available file="build/verify/tar/${release.root}/README.md"
               type="file"
               property="tar.readme.ok" />

    <fail unless="zip.readme.ok"
          message="README is missing from ZIP." />

    <fail unless="tar.readme.ok"
          message="README is missing from TAR.GZ." />
</target>
~~~

Có thể mở archive bằng công cụ tương ứng để xem danh sách entry. Trên Linux/macOS thường dùng `unzip -l`, `tar -tf` hoặc `gzip -t`; trên Windows có thể dùng công cụ giải nén hỗ trợ ZIP/TAR/GZip.

Khi kiểm tra TAR.GZ, cần xác nhận cả hai lớp: file GZip giải nén được và nội dung TAR bên trong có danh sách file đúng.

## 15. Tính nhất quán và khả năng tái tạo gói phát hành

Hai lần build cùng mã nguồn không nhất thiết tạo ra byte archive giống hệt nhau nếu timestamp, thứ tự file, metadata hoặc môi trường khác nhau. Nếu cần so sánh checksum hoặc tạo artifact có thể tái lập, hãy kiểm soát:

- Phiên bản JDK và Ant.
- Phiên bản dependency được đóng gói.
- Nội dung staging và thứ tự/nguồn file.
- Timestamp được ghi trong archive nếu công cụ và cấu hình hỗ trợ chuẩn hóa.
- Quyền file và metadata TAR.
- Encoding tên file trong ZIP.
- Các file môi trường, log và file tạm bị loại khỏi gói.

Không nên tự ý chỉnh timestamp hoặc metadata nếu yêu cầu phân phối cần giữ thời gian sửa đổi thực tế. Hãy xác định mục tiêu: lưu dấu vết thời gian gốc hay tạo archive có thể tái lập để so sánh byte-for-byte.

Đối với gói phát hành, nên tạo staging mới từ đầu hoặc dọn sạch staging trước khi tập hợp file. Nếu chỉ ghi thêm vào staging cũ, file đã bị xóa khỏi source có thể vẫn còn trong gói mới.

## 16. Tạo checksum cho artifact

Sau khi tạo archive, có thể tạo checksum để người nhận xác nhận file tải xuống không bị thay đổi. Ant có task checksum.

Ví dụ tạo SHA-256:

~~~xml
<checksum file="${dist.dir}/${release.root}.zip"
          algorithm="SHA-256"
          fileext=".sha256" />

<checksum file="${dist.dir}/${release.root}.tar.gz"
          algorithm="SHA-256"
          fileext=".sha256" />
~~~

Kết quả là các file checksum cạnh archive. Người nhận có thể tính lại SHA-256 và so sánh với giá trị đã công bố.

Checksum giúp phát hiện lỗi truyền tải hoặc thay đổi ngoài ý muốn; nó không chứng minh nguồn phát hành là đáng tin cậy nếu checksum được lấy từ cùng một kênh không an toàn. Với yêu cầu xác thực nguồn gốc, cần ký artifact hoặc checksum bằng cơ chế chữ ký số phù hợp.

## 17. Lỗi thường gặp khi đóng gói

### 17.1. Archive rỗng hoặc thiếu file

Kiểm tra basedir, dir của FileSet và các mẫu include/exclude. Mẫu được tính tương đối với thư mục gốc, không phải thư mục làm việc của shell.

### 17.2. Đường dẫn bên trong archive sai

Dùng prefix của ZipFileSet hoặc TarFileSet để điều khiển thư mục gốc. Nếu file được đặt ở sai vị trí, kiểm tra basedir và đường dẫn tương đối trước khi thêm các thao tác đổi tên phức tạp.

### 17.3. File cũ vẫn còn trong ZIP

Nếu update=true, entry cũ không có trong source mới có thể vẫn tồn tại. Tạo lại archive từ đầu khi cần nội dung phản ánh chính xác staging hiện tại.

### 17.4. Script không chạy được sau khi giải nén TAR

Kiểm tra filemode của TarFileSet. Script shell thường cần quyền thực thi như 755. ZIP không phải lúc nào cũng bảo toàn quyền Unix theo cách nhất quán giữa các công cụ giải nén.

### 17.5. Tên file dài bị lỗi trong TAR

Chọn longfile="posix" hoặc "gnu" tùy hệ thống đích hỗ trợ. Tránh truncate nếu cần giữ nguyên tên file.

### 17.6. Nén TAR hai lần

Nếu đã dùng compression="gzip" trong task tar, không gọi gzip thêm lần nữa trên kết quả. Hãy chọn một trong hai cách: tar nén trực tiếp hoặc tar không nén rồi gzip riêng.

### 17.7. JAR chạy không tìm thấy dependency

Kiểm tra manifest Class-Path hoặc script khởi chạy. JAR không tự bao gồm các thư viện ngoài chỉ vì chúng nằm trong thư mục lib của dự án.

### 17.8. Gói phát hành chứa file nhạy cảm

Kiểm tra staging và các mẫu FileSet. Loại file cấu hình cá nhân, secret, log, cache, file tạm và dữ liệu test khỏi archive.

### 17.9. ZIP chứa entry trùng tên

Nhiều FileSet có thể cùng thêm một đường dẫn. Dùng prefix riêng hoặc cấu hình chính sách duplicate để phát hiện và xử lý xung đột.

## 18. Thực hành tốt

- **Tạo staging trước khi archive.** Tập hợp các file cần phát hành vào một cây thư mục dễ kiểm tra.
- **Đặt tên artifact theo phiên bản.** Ví dụ inventory-1.4.0.zip và inventory-1.4.0.tar.gz.
- **Dùng include/exclude rõ ràng.** Loại file tạm, log, backup, dữ liệu cá nhân và secret.
- **Dùng prefix để kiểm soát cấu trúc archive.** Đảm bảo khi giải nén có thư mục gốc nhất quán.
- **Chọn định dạng theo môi trường người nhận.** ZIP phù hợp trao đổi đa nền tảng; TAR.GZ thường phù hợp phân phối trên Linux/Unix.
- **Giữ quyền thực thi trong TAR.** Đặt filemode và dirmode phù hợp, không cấp quyền quá rộng.
- **Chọn longfile theo hệ thống đích.** Dùng PAX hoặc GNU extension khi cần tên đường dẫn dài.
- **Không dùng update cho archive cần phản ánh chính xác staging.** Tạo mới để tránh entry cũ còn sót.
- **Tách archive và compression trong tư duy.** ZIP vừa gom vừa nén; TAR gom file; GZip/BZip2 nén một luồng.
- **Kiểm tra archive sau khi tạo.** Giải nén vào thư mục tạm và xác nhận file quan trọng có mặt.
- **Tạo checksum hoặc chữ ký khi phát hành.** Hỗ trợ kiểm tra tính toàn vẹn và nguồn gốc artifact.
- **Giữ build có thể tái lập.** Cố định dependency, công cụ, nội dung staging và metadata theo yêu cầu phát hành.

## 19. Kết luận

Apache Ant hỗ trợ tạo gói phân phối bằng nhiều định dạng. Task zip gom file và thư mục thành ZIP, ZipFileSet giúp đặt file vào cấu trúc đích bằng prefix hoặc fullpath. Task tar tạo archive TAR và có thể nén trực tiếp bằng gzip hoặc bzip2; TarFileSet cho phép chọn file và đặt quyền file/thư mục. Task gzip và bzip2 nén một file riêng, còn jar tạo Java Archive có thể chứa manifest cho ứng dụng hoặc thư viện.

Một quy trình phát hành đáng tin cậy nên biên dịch và kiểm thử trước, tạo staging sạch, chọn file bằng include/exclude, tạo archive với cấu trúc và metadata phù hợp, sau đó giải nén kiểm tra và tạo checksum. Chọn ZIP cho trao đổi đa nền tảng, TAR.GZ hoặc TAR.BZ2 cho môi trường Unix-like và JAR cho thành phần Java. Kiểm soát rõ nội dung, đường dẫn và quyền file giúp gói phát hành dễ cài đặt, an toàn và nhất quán.

## Tài liệu tham khảo

- [Apache Ant Zip Task](https://ant.apache.org/manual/Tasks/zip.html)
- [Apache Ant Tar Task](https://ant.apache.org/manual/Tasks/tar.html)
- [Apache Ant GZip Task](https://ant.apache.org/manual/Tasks/gzip.html)
- [Apache Ant BZip2 Task](https://ant.apache.org/manual/Tasks/bzip2.html)
- [Apache Ant Jar Task](https://ant.apache.org/manual/Tasks/jar.html)
- [Apache Ant Checksum Task](https://ant.apache.org/manual/Tasks/checksum.html)
- [Apache Ant Unzip Task](https://ant.apache.org/manual/Tasks/unzip.html)

