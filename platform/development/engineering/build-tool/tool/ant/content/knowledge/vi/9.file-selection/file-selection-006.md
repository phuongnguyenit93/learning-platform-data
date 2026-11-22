# Tái sử dụng PatternSet trong nhiều FileSet của Apache Ant

Khi buildfile cần chọn file theo nhiều quy tắc include và exclude, việc lặp lại cùng một danh sách mẫu trong từng FileSet làm cấu hình dài và khó bảo trì. Apache Ant cung cấp datatype PatternSet để gom các quy tắc chọn file thành một nhóm có thể đặt tên và tham chiếu lại.

PatternSet mô tả **những đường dẫn tương đối nào được chọn hoặc loại bỏ**. FileSet mô tả **thư mục gốc nào được quét** và sử dụng các quy tắc chọn file nào. Khi nhiều FileSet dùng chung một PatternSet, ta có thể áp dụng cùng chính sách chọn file cho nhiều thư mục nguồn hoặc thư mục tài nguyên mà không sao chép các mẫu.

## 1. Phân biệt PatternSet và FileSet

Hai thành phần thường được dùng cùng nhau nhưng có trách nhiệm khác nhau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| PatternSet | Lưu tập hợp mẫu include và exclude | Chọn file Java, loại file test và mã nguồn sinh tự động |
| FileSet | Chọn file trong một thư mục cơ sở cụ thể | Quét src/main/java hoặc src/legacy/java |
| Task tiêu thụ FileSet | Thực hiện công việc với các file đã chọn | copy, delete, zip hoặc jar |

Ví dụ một FileSet có thể quét thư mục src/main/resources và chỉ lấy file XML. PatternSet có thể lưu quy tắc **chỉ lấy file XML** đó để FileSet khác áp dụng cho thư mục tài nguyên thứ hai.

PatternSet không tự quét thư mục và cũng không thực hiện sao chép hay đóng gói. Nó chỉ chứa quy tắc. FileSet mới gắn quy tắc với một basedir để xác định tập file thực tế.

## 2. Khai báo một PatternSet có id

Có thể khai báo PatternSet ở cấp project, bên ngoài các target. Dùng thuộc tính id để đặt tên cho nhóm quy tắc:

~~~xml
<project name="inventory" default="package" basedir=".">
    <patternset id="production.java">
        <include name="**/*.java" />
        <exclude name="**/*Test.java" />
        <exclude name="**/generated/**" />
    </patternset>

    <!-- targets are declared below -->
</project>
~~~

Trong ví dụ:

- include name="**/*.java" chọn các file có phần mở rộng .java ở mọi cấp thư mục.
- exclude name="**/*Test.java" loại các file có tên kết thúc bằng Test.java.
- exclude name="**/generated/**" loại các file nằm bên dưới thư mục generated.

PatternSet có id production.java để các FileSet trong cùng project có thể tham chiếu bằng refid.

Một PatternSet có thể chứa nhiều phần tử include và exclude. Các mẫu include được kết hợp theo kiểu OR: file khớp ít nhất một mẫu include thì đủ điều kiện được chọn. Sau đó, nếu file khớp bất kỳ mẫu exclude nào, file bị loại khỏi tập kết quả.

Nếu PatternSet không có mẫu include, mặc định mọi file đều được xem là phù hợp với phần include; các mẫu exclude vẫn có thể loại file ra. Vì vậy, một PatternSet chỉ có exclude thường có nghĩa là lấy tất cả file trừ những file khớp mẫu loại trừ.

## 3. Tham chiếu PatternSet bằng refid trong nhiều FileSet

Sau khi khai báo PatternSet có id, đặt phần tử patternset với thuộc tính refid bên trong từng FileSet:

~~~xml
<project name="inventory" default="copy-sources" basedir=".">
    <patternset id="production.java">
        <include name="**/*.java" />
        <exclude name="**/*Test.java" />
        <exclude name="**/generated/**" />
    </patternset>

    <target name="copy-sources">
        <copy todir="build/sources">
            <fileset dir="src/main/java">
                <patternset refid="production.java" />
            </fileset>

            <fileset dir="src/legacy/java">
                <patternset refid="production.java" />
            </fileset>
        </copy>
    </target>
</project>
~~~

Task copy nhận hai FileSet:

1. FileSet thứ nhất quét src/main/java.
2. FileSet thứ hai quét src/legacy/java.
3. Cả hai cùng tham chiếu PatternSet production.java.
4. Mỗi FileSet áp dụng include và exclude trên đường dẫn tương đối của chính thư mục gốc đó.

Nhờ vậy, các file Java thông thường được chọn từ cả hai cây thư mục, trong khi file test và mã nguồn nằm dưới generated bị loại theo cùng một chính sách.

Để hiểu chính xác phạm vi, giả sử có cấu trúc:

~~~text
project/
├── build.xml
├── src/
│   ├── main/
│   │   └── java/
│   │       ├── com/example/App.java
│   │       ├── com/example/AppTest.java
│   │       └── generated/com/example/Mapper.java
│   └── legacy/
│       └── java/
│           ├── com/example/LegacyAdapter.java
│           └── com/example/LegacyTest.java
└── build/
~~~

Khi áp dụng production.java:

- App.java được chọn.
- AppTest.java bị loại bởi mẫu **/*Test.java.
- Mapper.java bị loại bởi mẫu **/generated/**.
- LegacyAdapter.java được chọn.
- LegacyTest.java bị loại bởi mẫu test.

PatternSet không chứa đường dẫn tuyệt đối của src/main/java hay src/legacy/java. Các mẫu được áp dụng tương đối với basedir của từng FileSet. Đây là lý do cùng một PatternSet có thể tái sử dụng cho nhiều thư mục khác nhau.

## 4. Hiểu cú pháp mẫu đường dẫn Ant

PatternSet sử dụng quy tắc mẫu đường dẫn của Ant. Các ký tự đại diện quan trọng là:

| Mẫu | Ý nghĩa |
|---|---|
| * | Khớp không hoặc nhiều ký tự trong một thành phần đường dẫn, không đi qua dấu phân cách thư mục |
| ? | Khớp đúng một ký tự trong một thành phần đường dẫn |
| ** | Khớp không hoặc nhiều cấp thư mục |
| **/*.java | Khớp file Java ở thư mục gốc hoặc trong các thư mục con |
| config/*.xml | Khớp file XML trực tiếp trong thư mục config |
| **/test/** | Khớp các file nằm trong thư mục test ở bất kỳ cấp nào |

Ví dụ:

~~~xml
<patternset id="resources">
    <include name="**/*.xml" />
    <include name="**/*.properties" />
    <exclude name="**/local/**" />
    <exclude name="**/*.example.properties" />
</patternset>
~~~

PatternSet resources chọn XML và Properties ở mọi cấp, sau đó loại các file nằm trong thư mục local và các file mẫu có hậu tố .example.properties.

Trong các mẫu Ant, nên dùng dấu gạch chéo xuôi / làm dấu phân cách đường dẫn, kể cả khi build chạy trên Windows. Ant xử lý mẫu theo cấu trúc đường dẫn của nó và chuyển đổi phù hợp với hệ điều hành.

Một số điều cần nhớ:

- **Mẫu được tính từ thư mục gốc của FileSet.** Nếu FileSet có dir="src/main/resources", mẫu config/*.xml tìm trong src/main/resources/config.
- **Một dấu * không đi qua nhiều thư mục.** Mẫu *.java chỉ chọn file Java ngay ở thư mục gốc, không chọn file trong package con.
- **Hai dấu ** dùng cho nhiều cấp.** Mẫu **/*.java bao phủ các thư mục con.
- **Mẫu include có thể lặp lại.** Nhiều include tạo thành tập hợp các lựa chọn được phép.
- **Exclude được áp dụng sau include.** File khớp exclude sẽ bị loại dù đã khớp một include.
- **Phân biệt hoa thường phụ thuộc cấu hình FileSet.** FileSet mặc định dùng chế độ phân biệt chữ hoa chữ thường; có thể điều chỉnh bằng thuộc tính casesensitive khi thực sự cần.

## 5. Dùng PatternSet chung trong các task khác nhau

Một lợi ích lớn của PatternSet là quy tắc chọn file không gắn với một task cụ thể. Nhiều task chấp nhận FileSet, vì vậy có thể dùng cùng PatternSet khi sao chép, tạo JAR, ZIP hoặc xóa file.

### 5.1. Sao chép tài nguyên

~~~xml
<patternset id="runtime.resources">
    <include name="**/*.xml" />
    <include name="**/*.properties" />
    <exclude name="**/local/**" />
    <exclude name="**/*-example.properties" />
</patternset>

<target name="copy-resources">
    <copy todir="build/resources">
        <fileset dir="src/main/resources">
            <patternset refid="runtime.resources" />
        </fileset>
        <fileset dir="src/shared/resources">
            <patternset refid="runtime.resources" />
        </fileset>
    </copy>
</target>
~~~

Hai thư mục tài nguyên được lọc theo cùng quy tắc. Nếu sau này cần loại thêm một nhóm file, chỉ cần cập nhật PatternSet runtime.resources; các FileSet đang tham chiếu sẽ dùng quy tắc đã sửa.

### 5.2. Đóng gói JAR

~~~xml
<patternset id="jar.contents">
    <include name="**/*.class" />
    <include name="**/*.xml" />
    <exclude name="**/*Test.class" />
    <exclude name="**/debug/**" />
</patternset>

<target name="package">
    <jar destfile="dist/inventory.jar">
        <fileset dir="build/classes">
            <patternset refid="jar.contents" />
        </fileset>
    </jar>
</target>
~~~

Trong ví dụ này, FileSet quét thư mục build/classes và chỉ đưa các file khớp jar.contents vào JAR. PatternSet quản lý chính sách lựa chọn; task jar thực hiện đóng gói.

### 5.3. Tạo ZIP phân phối

~~~xml
<patternset id="distribution.files">
    <include name="**/*.jar" />
    <include name="**/*.xml" />
    <include name="README.txt" />
    <exclude name="**/*-sources.jar" />
</patternset>

<target name="distribution">
    <zip destfile="dist/inventory-distribution.zip">
        <fileset dir="build/distribution">
            <patternset refid="distribution.files" />
        </fileset>
    </zip>
</target>
~~~

Khi chính sách chọn file cần thay đổi, chỉnh PatternSet distribution.files thay vì phải tìm và sửa các mẫu lặp lại trong từng task.

### 5.4. Xóa một nhóm file được chọn

PatternSet cũng có thể giới hạn phạm vi FileSet dùng cho task delete:

~~~xml
<patternset id="temporary.files">
    <include name="**/*.tmp" />
    <include name="**/*.bak" />
</patternset>

<target name="clean-temporary">
    <delete>
        <fileset dir="build">
            <patternset refid="temporary.files" />
        </fileset>
    </delete>
</target>
~~~

Target clean-temporary chỉ xóa file phù hợp với các mẫu trong build. Khi dùng delete, cần đặc biệt chú ý basedir và exclude để tránh chọn nhầm dữ liệu cần giữ lại.

## 6. Kết hợp nhiều PatternSet

Có thể xây dựng PatternSet dùng chung rồi tạo một PatternSet chuyên biệt bằng cách tham chiếu PatternSet nền và bổ sung quy tắc riêng.

Ví dụ, nhóm file Java cơ bản và nhóm mã nguồn production:

~~~xml
<patternset id="all.java">
    <include name="**/*.java" />
</patternset>

<patternset id="production.java">
    <patternset refid="all.java" />
    <exclude name="**/*Test.java" />
    <exclude name="**/generated/**" />
</patternset>
~~~

PatternSet production.java kế thừa các mẫu từ all.java bằng cách nhúng tham chiếu, rồi bổ sung các mẫu exclude. Điều này giúp chia quy tắc thành phần dùng chung và phần đặc thù.

Có thể tiếp tục tạo bộ lọc cho mã nguồn kiểm thử:

~~~xml
<patternset id="test.java">
    <patternset refid="all.java" />
    <include name="**/*Test.java" />
</patternset>
~~~

Khi cần áp dụng, mỗi FileSet tham chiếu đúng PatternSet:

~~~xml
<copy todir="build/main-sources">
    <fileset dir="src">
        <patternset refid="production.java" />
    </fileset>
</copy>

<copy todir="build/test-sources">
    <fileset dir="src">
        <patternset refid="test.java" />
    </fileset>
</copy>
~~~

Việc tổ chức PatternSet theo lớp như vậy hữu ích khi có một tập mẫu chung và nhiều biến thể lựa chọn. Tuy nhiên, không nên tạo quá nhiều tầng tham chiếu khiến người đọc phải mở nhiều định nghĩa mới biết file nào được chọn.

## 7. Nạp include/exclude từ file bên ngoài

Khi danh sách mẫu dài hoặc được nhiều buildfile chia sẻ, PatternSet có thể đọc danh sách từ file bằng includesfile và excludesfile.

Ví dụ:

~~~xml
<patternset id="release.files">
    <includesfile name="config/release-includes.txt" />
    <excludesfile name="config/release-excludes.txt" />
</patternset>
~~~

File config/release-includes.txt:

~~~text
**/*.jar
**/*.xml
README.md
~~~

File config/release-excludes.txt:

~~~text
**/*-sources.jar
**/debug/**
**/local/**
~~~

PatternSet đọc các mẫu từ hai file đó, sau đó FileSet tham chiếu PatternSet như bình thường:

~~~xml
<zip destfile="dist/release.zip">
    <fileset dir="build/distribution">
        <patternset refid="release.files" />
    </fileset>
</zip>
~~~

Cách này giúp nhóm có thể điều chỉnh danh sách file được đóng gói mà không cần sửa XML. Hãy quản lý hai file danh sách cùng phiên bản với buildfile và ghi rõ ý nghĩa từng nhóm mẫu.

## 8. Các điểm cần lưu ý khi tái sử dụng

### 8.1. Một PatternSet, nhiều basedir

Cùng một PatternSet có thể được áp dụng cho các thư mục gốc khác nhau. Tuy nhiên, mẫu luôn được tính tương đối với basedir của từng FileSet. Nếu cấu trúc hai thư mục không tương đồng, cùng một mẫu có thể chọn ra các tập file khác nhau hoặc không chọn được file nào.

### 8.2. Không nhầm id với refid

- id đặt tên cho PatternSet được định nghĩa.
- refid tham chiếu đến PatternSet đã có.

Ví dụ:

~~~xml
<patternset id="web.resources">
    <include name="**/*.css" />
    <include name="**/*.js" />
</patternset>

<fileset dir="src/main/webapp">
    <patternset refid="web.resources" />
</fileset>
~~~

Không dùng refid như một tên mới để khai báo nhóm quy tắc. Định nghĩa phải có id; nơi sử dụng mới tham chiếu bằng refid.

### 8.3. Tránh sửa quy tắc ở nhiều nơi

Nếu cùng một bộ lọc được sao chép vào nhiều FileSet, một thay đổi có thể bị bỏ sót ở một nơi. Đưa quy tắc dùng chung vào PatternSet giúp giảm sự lệch nhau giữa các task.

### 8.4. Hiểu default excludes của FileSet

FileSet thường áp dụng danh sách default excludes của Ant để bỏ qua một số file metadata và thư mục quản lý phiên bản. Do đó, kết quả quét thực tế có thể không bao gồm một file dù mẫu include của PatternSet có vẻ khớp. Thuộc tính defaultexcludes của FileSet cho phép kiểm soát hành vi này; chỉ tắt nó khi có lý do rõ ràng.

### 8.5. Cẩn thận khi dùng PatternSet cho thao tác xóa

Một PatternSet có thể được dùng cho cả copy và delete, nhưng ý nghĩa của sai sót rất khác nhau. Với delete, hãy giới hạn basedir chặt chẽ, thử chọn file bằng một task không phá hủy hoặc xem log trước khi áp dụng trên dữ liệu quan trọng.

### 8.6. Giữ chính sách chọn file dễ hiểu

Tên PatternSet nên thể hiện mục đích như production.java, runtime.resources, test.java hoặc distribution.files. Tránh tên quá chung như common hay filter nếu project có nhiều nhóm quy tắc.

## 9. Khi nào nên dùng PatternSet dùng chung?

Nên tách PatternSet thành định nghĩa có id khi:

- Nhiều FileSet cần cùng danh sách include/exclude.
- Nhiều task như copy, jar và zip phải áp dụng cùng chính sách chọn file.
- Một dự án có nhiều thư mục nguồn nhưng muốn lọc file nhất quán.
- Danh sách mẫu đủ dài để cần đặt tên và quản lý riêng.
- Các biến thể lọc có thể được xây dựng từ một bộ mẫu nền.

Nếu chỉ có một FileSet với một hoặc hai mẫu đơn giản, khai báo include và exclude trực tiếp bên trong FileSet có thể dễ đọc hơn. Tái sử dụng chỉ có lợi khi nó làm giảm lặp lại và giúp người đọc hiểu chính sách chọn file nhanh hơn.

## 10. Kết luận

PatternSet gom các quy tắc include và exclude thành một nhóm có tên. FileSet kết hợp nhóm quy tắc đó với một thư mục cơ sở để tạo tập file cụ thể. Định nghĩa PatternSet bằng id ở cấp project, sau đó tham chiếu bằng refid trong nhiều FileSet, giúp áp dụng nhất quán một chính sách chọn file cho nhiều thư mục và task.

Khi thiết kế, hãy nhớ rằng mẫu được tính tương đối với basedir của từng FileSet; include xác định những file có thể được chọn, exclude loại bỏ các file không mong muốn. Đặt tên PatternSet theo mục đích, tổ chức các bộ lọc dùng chung và kiểm tra kỹ basedir trước khi chạy các task có tác dụng phá hủy như delete.
