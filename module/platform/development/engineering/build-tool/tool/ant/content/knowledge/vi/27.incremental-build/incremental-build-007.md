# Dùng checksum khi dấu thời gian không phản ánh thay đổi nội dung

Trong một build tăng dần, Apache Ant thường so sánh thời điểm sửa đổi của tệp nguồn và tệp đầu ra để quyết định có cần chạy lại một bước hay không. Cách làm này nhanh và phù hợp với phần lớn dự án. Tuy nhiên, timestamp chỉ cho biết hệ thống tệp ghi nhận thời điểm nào tệp được sửa; nó không chứng minh nội dung của tệp có thay đổi hay không.

Có những trường hợp nội dung đã thay đổi nhưng timestamp vẫn giữ nguyên, hoặc timestamp thay đổi dù nội dung không đổi. Khi đó, quyết định dựa trên thời gian có thể bỏ qua một thay đổi cần build lại hoặc chạy build thừa. Để so sánh nội dung, có thể dùng **checksum**: một giá trị băm được tính từ byte của tệp.

Ant cung cấp task `<checksum>` để tính checksum cho một tệp hoặc một tập tệp. Khi lưu checksum của lần build trước và so sánh với checksum hiện tại, build file có thể xác định nội dung đầu vào đã thay đổi hay chưa, kể cả khi timestamp không phản ánh đúng thay đổi.

Sau bài học, bạn có thể:

- Hiểu giới hạn của kiểm tra timestamp trong build tăng dần.
- Phân biệt timestamp, checksum và checksum sidecar.
- Tính checksum bằng task `<checksum>` của Ant.
- Lưu digest giữa các lần build và so sánh với nội dung hiện tại.
- Chỉ chạy lại target khi nội dung đầu vào thay đổi hoặc đầu ra bị thiếu.
- Tính checksum cho nhiều tệp bằng FileSet và `totalproperty`.
- Kết hợp checksum với property, condition và target `unless`.
- Kiểm tra tính toàn vẹn của artifact bằng checksum file.
- Cân nhắc chi phí I/O, phạm vi đầu vào và các tham số ảnh hưởng đến kết quả build.

## 1. Timestamp trong build tăng dần

Build tăng dần (incremental build) chỉ thực hiện lại những bước có đầu vào thay đổi hoặc đầu ra không còn hợp lệ. Thay vì biên dịch và đóng gói mọi thứ ở mỗi lần chạy, build tool kiểm tra trạng thái đầu vào để bỏ qua công việc không cần thiết.

Một quy tắc phổ biến là so sánh timestamp của nguồn và đích:

```text
source.java  --mới hơn-->  source.class
     |                         |
     +------ cần compile ------+
```

Nếu tệp nguồn mới hơn tệp `.class`, compiler có thể cần chạy lại. Nếu tệp `.class` mới hơn hoặc cùng thời điểm, công cụ có thể coi đầu ra vẫn còn hiệu lực.

Trong Ant, nhiều task và datatype sử dụng timestamp để quyết định công việc. Ví dụ:

- `<javac>` chỉ biên dịch lại các lớp được xem là cần cập nhật.
- `<uptodate>` đặt property nếu các tệp đích đã cập nhật so với nguồn.
- `<copy>` có thể bỏ qua tệp đích đã mới hơn nguồn, tùy thuộc các thuộc tính và cấu hình.
- Các target có thể được điều kiện hóa bằng property được tính từ trạng thái tệp.

Timestamp là một tín hiệu hiệu quả, nhưng nó không phải dấu vân tay nội dung.

## 2. Vì sao timestamp có thể không phản ánh thay đổi nội dung?

Timestamp thường được lấy từ metadata của hệ thống tệp. Nó có thể bị giữ nguyên, làm tròn hoặc thay đổi bởi các công cụ khác với ứng dụng đã sửa nội dung.

### 2.1. Nội dung thay đổi nhưng timestamp được giữ nguyên

Một số công cụ sao chép hoặc khôi phục tệp có tùy chọn giữ thời điểm sửa đổi. Ví dụ:

1. Tệp `config.properties` có timestamp 10:00.
2. Một công cụ ghi nội dung mới vào tệp nhưng giữ timestamp 10:00.
3. Build tăng dần so sánh timestamp với đầu ra.
4. Vì timestamp không thay đổi, build có thể cho rằng đầu vào vẫn cũ và bỏ qua bước cần chạy lại.

Kết quả là đầu ra không còn tương ứng với nội dung nguồn hiện tại.

### 2.2. Độ phân giải timestamp thấp

Một số hệ thống tệp hoặc môi trường lưu trữ có độ phân giải thời gian thấp. Hai lần ghi rất gần nhau có thể được lưu cùng một timestamp hoặc timestamp bị làm tròn theo đơn vị lớn hơn độ chính xác thực tế.

Ví dụ, nếu timestamp chỉ phân biệt theo khoảng hai giây, hai phiên bản nội dung được ghi trong cùng khoảng đó có thể có thời điểm sửa đổi giống nhau. Build dựa trên so sánh thời gian có thể không nhận ra thay đổi.

### 2.3. Đồng hồ giữa các máy không đồng bộ

Khi nguồn và đầu ra nằm trên các máy hoặc filesystem khác nhau, đồng hồ có thể lệch nhau. Một tệp vừa được cập nhật có thể mang timestamp nhỏ hơn đầu ra do đồng hồ máy tạo ra nó chậm hơn.

Điều này thường gặp trong môi trường build phân tán, thư mục chia sẻ mạng, cache được đồng bộ hoặc artifact được giải nén từ một máy khác.

### 2.4. Timestamp thay đổi nhưng nội dung không đổi

Ngược lại, một thao tác copy, checkout hoặc giải nén có thể tạo timestamp mới cho tệp dù byte nội dung giống hệt trước đó. Build dựa trên thời gian có thể chạy lại một bước tốn kém dù đầu vào thực tế không đổi.

### 2.5. Đầu ra được tạo lại từ cùng nội dung

Một công cụ có thể ghi lại tệp đầu ra với nội dung giống hệt nhưng timestamp mới. Lần build sau có thể phải kiểm tra hoặc tạo lại nhiều đầu ra hơn cần thiết, tùy cơ chế incremental của task.

### 2.6. Bảng so sánh

| Tình huống | Timestamp | Nội dung | Rủi ro với build tăng dần |
|---|---|---|---|
| Sửa tệp bình thường | Thay đổi | Thay đổi | Thường được phát hiện. |
| Sửa nội dung nhưng khôi phục timestamp | Không đổi | Thay đổi | Có thể bỏ qua bước cần chạy lại. |
| Hai lần ghi trong cùng độ phân giải thời gian | Có thể giống nhau | Thay đổi | Có thể bỏ qua thay đổi. |
| Đồng hồ máy nguồn chậm hơn máy tạo đầu ra | Có thể nhỏ hơn | Thay đổi | Có thể coi đầu vào chưa mới. |
| Copy giữ nguyên timestamp | Không đổi | Có thể thay đổi | Có thể bỏ qua thay đổi. |
| Touch hoặc giải nén lại cùng byte | Thay đổi | Không đổi | Có thể chạy build thừa. |

## 3. Checksum là gì?

Checksum là giá trị được tính từ nội dung byte của tệp bằng một thuật toán. Với cùng một thuật toán, cùng một chuỗi byte sẽ tạo ra cùng một digest. Khi nội dung thay đổi, digest gần như chắc chắn thay đổi đối với các thuật toán băm mạnh như SHA-256.

Ví dụ minh họa:

```text
Nội dung A:  app.mode=development
SHA-256:    4d... (digest minh họa)

Nội dung B:  app.mode=production
SHA-256:    a8... (digest minh họa)
```

Hai nội dung có thể có timestamp giống nhau, nhưng checksum khác nhau vì byte đầu vào khác nhau.

### 3.1. Checksum so với timestamp

| Đặc điểm | Timestamp | Checksum |
|---|---|---|
| Dựa trên | Metadata thời điểm sửa đổi. | Byte nội dung. |
| Phát hiện nội dung đổi nhưng giữ timestamp | Không đáng tin cậy. | Có thể phát hiện. |
| Phát hiện timestamp đổi nhưng nội dung giống nhau | Không; thường coi là mới hơn. | Digest vẫn giống nhau. |
| Chi phí kiểm tra | Thấp, chủ yếu đọc metadata. | Phải đọc nội dung và tính digest. |
| Phù hợp | Build thông thường, kiểm tra nhanh. | Đầu vào có timestamp không đáng tin hoặc cần xác minh nội dung. |

Checksum không nhất thiết thay thế toàn bộ kiểm tra timestamp. Một build có thể dùng timestamp để sàng lọc nhanh và checksum cho những đầu vào quan trọng hoặc những bước mà timestamp không đủ tin cậy.

### 3.2. Thuật toán băm

Ant `<checksum>` dùng thuật toán được hỗ trợ bởi Java `MessageDigest`. Thuộc tính `algorithm` cho phép chỉ định thuật toán.

Ví dụ:

```xml
<checksum file="src/config/app.properties"
          algorithm="SHA-256"
          property="app.config.digest" />
```

Các thuật toán thường gặp gồm:

- `MD5`
- `SHA-1`
- `SHA-256`
- Các thuật toán khác nếu JDK và provider hiện tại hỗ trợ.

Ant có thể dùng MD5 làm mặc định nếu không chỉ định thuật toán. Với build mới, nên chỉ định rõ `SHA-256` để tránh phụ thuộc vào mặc định và sử dụng thuật toán có biên độ an toàn tốt hơn.

Checksum trong bài học được dùng để nhận biết thay đổi nội dung và kiểm tra tính toàn vẹn. Nó không tự chứng minh ai đã tạo tệp. Nếu cần xác thực nguồn gốc artifact, hãy dùng chữ ký số hoặc cơ chế xác thực artifact phù hợp.

## 4. Task `<checksum>` của Ant

Task `<checksum>` tính digest cho một tệp hoặc một tập tệp. Kết quả có thể được ghi ra checksum file, lưu vào property hoặc dùng để xác minh checksum đã có.

### 4.1. Tính checksum và ghi ra file

Ví dụ:

```xml
<checksum file="build/dist/sample-app.jar"
          algorithm="SHA-256"
          fileext=".sha256" />
```

Ant tính checksum của JAR và ghi kết quả ra một tệp sidecar cạnh artifact. Với cấu hình trên, tên sidecar được tạo bằng cách nối phần mở rộng `.sha256` vào tên tệp nguồn, theo quy tắc của task.

Checksum sidecar có thể được lưu cùng artifact để người nhận kiểm tra sau khi tải xuống hoặc sao chép.

### 4.2. Lưu checksum vào property

Nếu chỉ cần digest trong lần build hiện tại, dùng thuộc tính `property`:

```xml
<checksum file="src/config/app.properties"
          algorithm="SHA-256"
          property="current.config.digest" />

<echo message="Current digest: ${current.config.digest}" />
```

Ant đặt property `current.config.digest` bằng giá trị digest vừa tính. Property này chỉ tồn tại trong lần chạy Ant hiện tại; nó không tự được lưu để so sánh ở lần build sau.

Để dùng checksum cho build tăng dần qua nhiều lần chạy, cần lưu digest vào một tệp trạng thái hoặc cơ chế cache bền vững khác, rồi đọc lại ở lần chạy tiếp theo.

### 4.3. Xác minh checksum sidecar bằng `verifyproperty`

Task `<checksum>` cũng có thể kiểm tra tệp nguồn có khớp với checksum sidecar đã tồn tại hay không:

```xml
<checksum file="build/dist/sample-app.jar"
          algorithm="SHA-256"
          fileext=".sha256"
          verifyproperty="artifact.checksum.valid" />
```

`verifyproperty` là tên property mà Ant đặt kết quả xác minh. Giá trị cho biết checksum hiện tại có khớp với sidecar hay không. Thuộc tính này dùng cho chế độ xác minh; không kết hợp nó với `property` trong cùng một lần gọi task.

Có thể dừng build nếu xác minh thất bại:

```xml
<checksum file="build/dist/sample-app.jar"
          algorithm="SHA-256"
          fileext=".sha256"
          verifyproperty="artifact.checksum.valid" />

<condition property="artifact.checksum.invalid">
    <equals arg1="${artifact.checksum.valid}" arg2="false" />
</condition>

<fail if="artifact.checksum.invalid"
      message="Artifact checksum verification failed" />
```

`fail` dừng build nếu property invalid được đặt. Hãy bảo đảm sidecar đã được tạo hoặc lấy về trước bước xác minh.

### 4.4. Các thuộc tính hữu ích

| Thuộc tính | Công dụng |
|---|---|
| `file` | Tệp đơn cần tính hoặc xác minh checksum. |
| `todir` | Thư mục đích chứa checksum sidecar khi xử lý tệp/tập tệp. |
| `algorithm` | Thuật toán băm, ví dụ `SHA-256`. |
| `fileext` | Phần mở rộng cho checksum file. |
| `property` | Property nhận digest của tệp được tính. |
| `verifyproperty` | Property nhận kết quả xác minh checksum sidecar. |
| `totalproperty` | Property nhận checksum tổng hợp của tập tệp được chọn. |
| `forceOverwrite` | Điều khiển việc ghi lại checksum file khi task có thể bỏ qua do timestamp. |
| `readbuffersize` | Kích thước buffer đọc khi tính checksum. |

Các thuộc tính `property` và `verifyproperty` phục vụ hai chế độ khác nhau. Hãy chọn chế độ phù hợp với mục tiêu: lấy digest để so sánh, hoặc xác minh một sidecar đã có.

## 5. Lưu digest giữa các lần build

Để checksum giúp quyết định có cần build lại hay không, cần một nơi lưu digest của lần xử lý thành công trước đó.

Một tệp trạng thái đơn giản có thể chứa digest:

```text
build/state/app-properties.sha256
```

Ở lần chạy tiếp theo, build file đọc digest cũ, tính digest hiện tại rồi so sánh hai giá trị.

```text
                 input file
                     |
                     v
               SHA-256 hiện tại
                     |
                     v
             so sánh với digest cũ
                     |
            +--------+--------+
            |                 |
         giống nhau         khác nhau
            |                 |
            v                 v
         bỏ qua            chạy lại task
                              |
                              v
                       lưu digest mới
```

Điểm quan trọng: checksum task tự tính digest, nhưng không tự ghi nhớ digest của lần build trước nếu bạn chỉ dùng `property`. Build file phải lưu trạng thái và đọc lại nó ở lần chạy sau.

## 6. Ví dụ incremental build bằng checksum cho một tệp

Giả sử dự án sao chép một tệp cấu hình vào thư mục generated. Nếu timestamp nguồn không đáng tin, ta muốn chỉ copy lại khi byte nội dung thay đổi hoặc đầu ra chưa tồn tại.

### 6.1. Cấu trúc thư mục

```text
checksum-demo/
├── build.xml
├── src/
│   └── config.properties
└── build/
    ├── generated/
    └── state/
        └── config.sha256
```

Tệp nguồn `src/config.properties`:

```properties
app.name=SampleApp
app.environment=development
```

### 6.2. Build file

```xml
<project name="checksum-demo" default="generate-config" basedir=".">
    <property name="input.file" location="src/config.properties" />
    <property name="generated.dir" location="build/generated" />
    <property name="generated.file" location="${generated.dir}/config.properties" />
    <property name="state.dir" location="build/state" />
    <property name="state.file" location="${state.dir}/config.sha256" />

    <target name="check-config">
        <available file="${state.file}" property="state.exists" />
        <available file="${generated.file}" property="output.exists" />

        <loadfile property="previous.digest"
                  srcFile="${state.file}"
                  failonerror="false" />

        <checksum file="${input.file}"
                  algorithm="SHA-256"
                  property="current.digest" />

        <condition property="config.unchanged">
            <and>
                <isset property="state.exists" />
                <isset property="output.exists" />
                <isset property="previous.digest" />
                <equals arg1="${current.digest}"
                        arg2="${previous.digest}"
                        trim="true" />
            </and>
        </condition>
    </target>

    <target name="generate-config"
            depends="check-config"
            unless="config.unchanged">
        <mkdir dir="${generated.dir}" />
        <mkdir dir="${state.dir}" />

        <copy file="${input.file}"
              tofile="${generated.file}"
              overwrite="true" />

        <!-- Chỉ ghi digest sau khi bước tạo đầu ra thành công. -->
        <echo file="${state.file}" message="${current.digest}" />
        <echo message="Configuration copied because content changed or output was missing." />
    </target>
</project>
```

### 6.3. Giải thích luồng xử lý

Target `check-config` thực hiện các việc sau:

1. Kiểm tra tệp digest trạng thái có tồn tại hay không.
2. Kiểm tra tệp đầu ra có tồn tại hay không.
3. Đọc digest của lần xử lý trước bằng `<loadfile>`.
4. Tính digest hiện tại của nguồn bằng `<checksum>`.
5. Đặt property `config.unchanged` chỉ khi trạng thái cũ, đầu ra và digest trước đều có, đồng thời hai digest giống nhau.

Target `generate-config` phụ thuộc `check-config`. Nếu `config.unchanged` đã được đặt, thuộc tính `unless` khiến target được bỏ qua. Nếu property chưa được đặt, Ant chạy task copy rồi ghi digest hiện tại vào tệp trạng thái.

Việc ghi digest sau khi copy thành công rất quan trọng. Nếu ghi trạng thái mới trước khi tạo đầu ra, một lỗi giữa chừng có thể khiến lần build sau tưởng rằng nội dung đã được xử lý thành công dù đầu ra chưa hoàn chỉnh.

### 6.4. Hành vi qua các lần chạy

| Tình huống | Digest trước | Digest hiện tại | Đầu ra | Kết quả |
|---|---|---|---|---|
| Lần chạy đầu tiên | Chưa có | Được tính | Chưa có | Chạy copy và lưu digest. |
| Không đổi nội dung | Có | Giống digest cũ | Có | Bỏ qua target tạo đầu ra. |
| Nội dung đổi, timestamp giữ nguyên | Có | Khác digest cũ | Có | Chạy copy lại và cập nhật digest. |
| Timestamp đổi nhưng byte giống nhau | Có | Giống digest cũ | Có | Bỏ qua copy. |
| Đầu ra bị xóa | Có | Giống digest cũ | Không có | Chạy copy lại. |
| Tệp trạng thái bị xóa | Chưa có | Được tính | Có thể có | Chạy copy và tạo lại trạng thái. |

Trong ví dụ, `<loadfile failonerror="false">` cho phép lần build đầu tiên tiếp tục khi tệp trạng thái chưa tồn tại. Nếu tệp nguồn không tồn tại, `<checksum>` vẫn báo lỗi vì không thể tính digest cho đầu vào bắt buộc.

### 6.5. Property Ant và trạng thái giữa các lần chạy

`current.digest`, `previous.digest` và `config.unchanged` là property của một lần chạy Ant. Chúng không tồn tại tự động sau khi tiến trình Ant kết thúc.

Chỉ tệp `build/state/config.sha256` được giữ lại trên đĩa để lần chạy sau đọc. Nếu target `clean` xóa toàn bộ `build`, trạng thái checksum cũng bị xóa và lần build kế tiếp sẽ xử lý lại đầu vào.

Nếu muốn giữ trạng thái incremental qua `clean`, hãy đặt state cache ở vị trí riêng và chỉ xóa nó bằng một target dọn cache chuyên biệt. Tuy nhiên, giữ state sau khi xóa output có thể không đem lại lợi ích vì output không còn tồn tại; điều kiện kiểm tra output trong ví dụ vẫn buộc tạo lại.

## 7. Tính checksum cho nhiều tệp bằng FileSet

Một bước build thường phụ thuộc vào nhiều tệp, chẳng hạn mã nguồn Java, tài nguyên, schema hoặc cấu hình. Task `<checksum>` hỗ trợ các FileSet lồng nhau.

Ví dụ tính checksum tổng hợp cho toàn bộ cấu hình:

```xml
<checksum algorithm="SHA-256"
          totalproperty="config.set.digest">
    <fileset dir="src/config">
        <include name="**/*.properties" />
        <include name="**/*.xml" />
        <include name="**/*.yml" />
    </fileset>
</checksum>

<echo message="Configuration set digest: ${config.set.digest}" />
```

`totalproperty` yêu cầu Ant tính một digest tổng hợp từ tập tệp được chọn và lưu vào property. Điều này hữu ích khi muốn có một fingerprint cho cả nhóm đầu vào thay vì quản lý từng digest riêng.

### 7.1. Giới hạn phạm vi FileSet

Phạm vi FileSet là một phần của logic incremental. Nếu task thực tế đọc cả `.properties` và `.xml` nhưng checksum chỉ chọn `.properties`, thay đổi XML sẽ không làm fingerprint đổi.

Hãy chọn đúng tập đầu vào:

```xml
<checksum algorithm="SHA-256"
          totalproperty="compile.inputs.digest">
    <fileset dir="src/main/java">
        <include name="**/*.java" />
    </fileset>
    <fileset dir="src/main/resources">
        <include name="**/*" />
    </fileset>
    <fileset dir="config">
        <include name="compiler-options.properties" />
    </fileset>
</checksum>
```

Trong ví dụ, fingerprint phụ thuộc vào mã nguồn Java, tài nguyên và tệp cấu hình compiler được chọn. Nếu build còn đọc schema, file sinh mã, template hoặc tệp khác, cần thêm chúng vào tập đầu vào.

### 7.2. Include và exclude

Có thể loại các tệp không ảnh hưởng đến đầu ra:

```xml
<checksum algorithm="SHA-256"
          totalproperty="source.digest">
    <fileset dir="src">
        <include name="**/*.java" />
        <exclude name="**/generated/**" />
        <exclude name="**/test/**" />
    </fileset>
</checksum>
```

Chỉ loại tệp khi chắc chắn bước build không phụ thuộc vào chúng. Nếu một tệp bị loại khỏi fingerprint nhưng lại ảnh hưởng đến kết quả, incremental build có thể bỏ qua công việc cần thiết.

### 7.3. Tên và vị trí tệp cũng có thể quan trọng

Checksum nội dung tập tệp phải được thiết kế phù hợp với cách task sử dụng đầu vào. Trong một số quy trình, đổi tên tệp hoặc chuyển thư mục có thể làm thay đổi kết quả dù byte của tệp không đổi, ví dụ khi tên file quyết định tên lớp sinh ra hoặc đường dẫn tài nguyên trong artifact.

Khi đó, fingerprint cần phản ánh cả cấu trúc đường dẫn hoặc manifest đầu vào, không chỉ nội dung byte. Hãy kiểm tra cách `totalproperty` của phiên bản Ant đang dùng tổng hợp tập tệp; nếu tên/đường dẫn có ý nghĩa đối với build, có thể tạo một manifest ổn định chứa đường dẫn tương đối cùng digest từng tệp rồi checksum manifest đó.

## 8. Đưa tham số build vào fingerprint

Checksum của mã nguồn không đủ nếu kết quả build còn phụ thuộc vào tham số khác. Ví dụ, cùng một mã nguồn có thể tạo bytecode khác nhau khi đổi:

- Phiên bản Java đích (`release`, `source`, `target`).
- Compiler arguments hoặc annotation processor.
- Phiên bản dependency trên classpath.
- Cấu hình lọc tài nguyên.
- Profile hoặc biến cấu hình được dùng trong bước generate.
- Phiên bản công cụ tạo mã.

Nếu những giá trị này thay đổi mà fingerprint chỉ bao gồm mã nguồn, build có thể dùng lại đầu ra cũ không còn phù hợp.

### 8.1. Tạo manifest tham số

Có thể ghi các tham số có ảnh hưởng vào một tệp manifest trạng thái:

```xml
<property name="java.release" value="17" />
<property name="compiler.mode" value="release" />

<target name="write-build-options">
    <mkdir dir="build/state" />
    <echo file="build/state/build-options.txt"
          message="java.release=${java.release}${line.separator}compiler.mode=${compiler.mode}${line.separator}" />
</target>
```

Sau đó thêm manifest vào tập được checksum:

```xml
<target name="calculate-input-digest" depends="write-build-options">
    <checksum algorithm="SHA-256"
              totalproperty="build.inputs.digest">
        <fileset dir="src/main/java">
            <include name="**/*.java" />
        </fileset>
        <fileset dir="build/state">
            <include name="build-options.txt" />
        </fileset>
    </checksum>
</target>
```

Trong ví dụ này, thay đổi mức Java hoặc compiler mode làm nội dung manifest thay đổi, do đó fingerprint cũng thay đổi. Tùy cấu trúc build, có thể thêm manifest dependency, resource và cấu hình công cụ tương tự.

### 8.2. Dependency version cũng là đầu vào

Nếu compiler hoặc generator dùng thư viện ngoài, thay đổi phiên bản dependency có thể làm kết quả khác dù mã nguồn không đổi. Fingerprint nên bao gồm thông tin dependency đã resolve, ví dụ một lockfile, manifest chứa tọa độ module/version hoặc checksum của các JAR liên quan.

Không nên chỉ đưa tên thư mục cache vào fingerprint. Cache có thể chứa nhiều phiên bản; điều cần ghi nhận là chính xác những artifact mà task sử dụng.

### 8.3. Không đưa mọi biến môi trường vào fingerprint

Chỉ đưa những biến có ảnh hưởng thực sự đến kết quả. Nếu thêm timestamp hiện tại, tên máy hoặc một biến không liên quan, fingerprint sẽ thay đổi ở mọi lần build và làm mất lợi ích incremental.

Ngược lại, bỏ sót một tham số có ảnh hưởng sẽ khiến build tái sử dụng đầu ra không còn hợp lệ. Cần hiểu rõ hợp đồng đầu vào của từng task hoặc generator.

## 9. Kết hợp checksum với target có điều kiện

Sau khi tính fingerprint, Ant có thể dùng `<condition>` để đặt property và thuộc tính `if`/`unless` của target để quyết định có chạy bước tạo đầu ra hay không.

Ví dụ khái quát:

```xml
<target name="check-inputs">
    <!-- Tính current.digest và đọc previous.digest. -->
    <condition property="inputs.changed">
        <not>
            <equals arg1="${current.digest}"
                    arg2="${previous.digest}"
                    trim="true" />
        </not>
    </condition>
</target>

<target name="regenerate" depends="check-inputs" if="inputs.changed">
    <!-- Chạy công cụ tạo đầu ra. -->
</target>
```

Trong ví dụ rút gọn, cần xử lý riêng lần đầu khi `previous.digest` chưa tồn tại và trường hợp đầu ra bị xóa. Ví dụ đầy đủ ở phần trước đã kiểm tra cả state file và output file trước khi đặt property `config.unchanged`.

### 9.1. `if` và `unless` kiểm tra sự tồn tại của property

Với target:

```xml
<target name="generate" unless="inputs.unchanged">
    ...
</target>
```

Ant bỏ qua target nếu property `inputs.unchanged` đã được đặt, bất kể giá trị chuỗi của nó là gì. Vì vậy, hãy chỉ đặt property này bằng `<condition>` khi biểu thức thật sự đúng.

Đừng dùng:

```xml
<property name="inputs.unchanged" value="false" />
```

để biểu thị false rồi kỳ vọng `unless` đọc giá trị boolean. Property đã tồn tại, nên target sẽ bị bỏ qua. Thay vào đó, chỉ tạo property khi điều kiện đúng.

### 9.2. Property bất biến và một lần chạy Ant

Ant property thông thường bất biến. Nếu target `check-inputs` đã đặt `inputs.unchanged`, không thể xóa property đó trong cùng lần build để ép target chạy lại sau khi một tệp thay đổi.

Đây không phải vấn đề với incremental build giữa các lần gọi Ant: mỗi tiến trình Ant mới tạo một project và tập property mới. Hãy thực hiện việc tính checksum và quyết định target trong cùng một lần chạy, với đầu vào ổn định trong suốt quá trình đó.

## 10. Xác minh artifact bằng checksum file

Ngoài việc quyết định build lại, checksum còn hữu ích để kiểm tra artifact sau khi đóng gói hoặc tải từ repository.

### 10.1. Tạo checksum cạnh artifact

```xml
<target name="write-artifact-checksum" depends="package">
    <checksum file="build/dist/sample-app.jar"
              algorithm="SHA-256"
              fileext=".sha256" />
</target>
```

Kết quả gồm artifact và tệp checksum đi kèm. Có thể lưu cả hai vào repository hoặc build artifacts.

### 10.2. Xác minh sau khi tải

Giả sử artifact và sidecar đã được tải vào thư mục `incoming`:

```xml
<target name="verify-downloaded-artifact">
    <checksum file="incoming/sample-app.jar"
              algorithm="SHA-256"
              fileext=".sha256"
              verifyproperty="download.valid" />

    <condition property="download.invalid">
        <equals arg1="${download.valid}" arg2="false" />
    </condition>

    <fail if="download.invalid"
          message="Downloaded artifact does not match its checksum file." />
</target>
```

Nếu checksum không khớp, build thất bại trước khi artifact được sử dụng ở bước tiếp theo.

### 10.3. Checksum không thay thế chữ ký số

Nếu artifact và checksum sidecar được tải từ cùng một nguồn không đáng tin cậy, kẻ tấn công có thể thay cả hai. Khi cần xác minh nguồn phát hành, phải dùng chữ ký số, chứng thư hoặc cơ chế provenance phù hợp.

SHA-256 phù hợp để phát hiện thay đổi nội dung và lỗi truyền tải thông thường. Nó không tự xác thực tác giả của artifact.

## 11. Chi phí và hiệu năng khi dùng checksum

Timestamp thường chỉ cần đọc metadata của tệp. Checksum phải đọc toàn bộ byte để tính digest. Với một tệp nhỏ, chi phí thường không đáng kể; với hàng nghìn tệp lớn hoặc source tree trên ổ mạng, việc tính checksum mỗi lần build có thể tốn thời gian I/O.

### 11.1. Chỉ checksum đầu vào cần thiết

Không cần checksum toàn bộ repository nếu target chỉ phụ thuộc vào một nhóm tệp. Hãy dùng FileSet với `include` và `exclude` chính xác.

Ví dụ, bước tạo tài liệu chỉ cần template và cấu hình:

```xml
<checksum algorithm="SHA-256"
          totalproperty="docs.inputs.digest">
    <fileset dir="docs/templates">
        <include name="**/*" />
    </fileset>
    <fileset dir="config/docs">
        <include name="*.properties" />
    </fileset>
</checksum>
```

Không đưa bytecode, ảnh hoặc tài nguyên không liên quan vào fingerprint của bước tạo tài liệu nếu task không đọc chúng.

### 11.2. Dùng timestamp để sàng lọc và checksum khi cần

Một chiến lược kết hợp có thể là:

1. Dùng timestamp để xác định những tệp có khả năng thay đổi.
2. Chỉ tính checksum cho nhóm đầu vào có timestamp không đáng tin hoặc cần kiểm tra nội dung chính xác.
3. So sánh digest đã lưu để quyết định có chạy lại bước tạo đầu ra không.

Tuy nhiên, nếu timestamp chính là tín hiệu không đáng tin trong môi trường của bạn, không nên dùng nó làm điều kiện duy nhất để quyết định có tính checksum hay không. Nếu chỉ checksum khi timestamp thay đổi, bạn vẫn bỏ sót trường hợp nội dung thay đổi nhưng timestamp được giữ nguyên.

### 11.3. Giữ cache ở vị trí ổn định

Nếu mỗi lần build đều xóa tệp trạng thái checksum, build sẽ phải xử lý lại tất cả đầu vào. Hãy phân biệt:

- Thư mục output có thể xóa và tạo lại.
- Thư mục state/cache dùng để ghi nhớ fingerprint giữa các lần build.
- Thư mục nguồn và cấu hình đầu vào.

State cache cần được gắn với đúng project, đúng loại đầu ra và đúng phiên bản công cụ. Nếu dùng chung một tệp digest cho hai target khác nhau, một target có thể vô tình bỏ qua việc xử lý cần thiết.

### 11.4. Kích thước buffer

Thuộc tính `readbuffersize` của `<checksum>` cho phép điều chỉnh kích thước buffer đọc. Với hầu hết dự án, giá trị mặc định là đủ. Chỉ thay đổi khi có số liệu đo cho thấy việc đọc checksum là nút thắt cổ chai.

## 12. Những lỗi thiết kế thường gặp

### 12.1. Chỉ tính checksum mà không lưu kết quả

Đoạn sau chỉ tạo digest trong lần chạy hiện tại:

```xml
<checksum file="src/config.properties"
          algorithm="SHA-256"
          property="current.digest" />
```

Nếu không lưu digest ra tệp hoặc cache bền vững, lần chạy tiếp theo không có giá trị cũ để so sánh. Muốn incremental qua nhiều lần build, phải có state được giữ lại.

### 12.2. Ghi digest trước khi tạo đầu ra thành công

Nếu lưu digest mới trước bước copy/generate, rồi bước đó thất bại, lần build tiếp theo có thể thấy digest đã khớp và bỏ qua việc tạo đầu ra. Hãy chỉ cập nhật state sau khi đầu ra được tạo thành công.

### 12.3. Không kiểm tra đầu ra có tồn tại

Nguồn không đổi không có nghĩa output chắc chắn còn tồn tại. Một người dùng có thể xóa output thủ công hoặc một bước clean có thể xóa nó. Điều kiện bỏ qua cần kiểm tra cả output.

### 12.4. Fingerprint không chứa đủ đầu vào

Nếu task phụ thuộc vào source, resource và compiler options nhưng checksum chỉ bao gồm source, thay đổi resource hoặc compiler options sẽ không làm fingerprint đổi. Hãy mô tả đầy đủ input set của task.

### 12.5. Dùng checksum như cơ chế xác thực nguồn gốc

Digest không phải chữ ký số. Nếu nguồn checksum không được xác thực, người khác có thể thay cả artifact và checksum. Dùng chữ ký/provenance khi cần xác minh nguồn phát hành.

### 12.6. Lưu state ở nơi bị clean xóa

Nếu target `clean` xóa cả state cache, lần build sau luôn coi như lần đầu. Điều này không sai về tính đúng đắn nhưng có thể làm mất lợi ích incremental. Hãy quyết định rõ state có nên được giữ lại hay không.

### 12.7. Dùng chung digest giữa các bước khác nhau

Hai target có thể đọc các tập đầu vào khác nhau. Mỗi target nên có state file riêng, ví dụ:

```text
build-state/
├── compile.inputs.sha256
├── docs.inputs.sha256
└── resources.inputs.sha256
```

Không dùng một property hoặc state file chung cho những bước có phạm vi đầu vào khác nhau.

## 13. Ví dụ tổng hợp: kiểm tra nội dung trước khi tạo tài nguyên

Ví dụ này có nhiều đầu vào: template, file cấu hình và một property chọn môi trường. Target tạo tài nguyên chỉ chạy khi fingerprint thay đổi hoặc đầu ra chưa có.

### 13.1. Cấu trúc dự án

```text
resource-build/
├── build.xml
├── config/
│   └── build.properties
├── templates/
│   └── app.properties.template
└── build/
    ├── generated/
    └── state/
```

Tệp `config/build.properties`:

```properties
app.name=SampleApp
```

Tệp `templates/app.properties.template`:

```properties
app.name=@APP_NAME@
app.environment=@ENVIRONMENT@
```

### 13.2. Build file

```xml
<project name="resource-build" default="generate" basedir=".">
    <property file="config/build.properties" />
    <property name="environment" value="development" />

    <property name="template.file" location="templates/app.properties.template" />
    <property name="config.file" location="config/build.properties" />
    <property name="generated.dir" location="build/generated" />
    <property name="generated.file" location="${generated.dir}/app.properties" />
    <property name="state.dir" location="build/state" />
    <property name="options.file" location="${state.dir}/generation-options.txt" />
    <property name="state.file" location="${state.dir}/generation.sha256" />

    <target name="write-options">
        <mkdir dir="${state.dir}" />
        <echo file="${options.file}"
              message="environment=${environment}${line.separator}app.name=${app.name}${line.separator}" />
    </target>

    <target name="check-inputs" depends="write-options">
        <available file="${state.file}" property="state.exists" />
        <available file="${generated.file}" property="output.exists" />

        <loadfile property="previous.digest"
                  srcFile="${state.file}"
                  failonerror="false" />

        <checksum algorithm="SHA-256"
                  totalproperty="current.digest">
            <fileset dir="templates">
                <include name="**/*" />
            </fileset>
            <fileset dir="config">
                <include name="**/*" />
            </fileset>
            <fileset dir="${state.dir}">
                <include name="generation-options.txt" />
            </fileset>
        </checksum>

        <condition property="inputs.unchanged">
            <and>
                <isset property="state.exists" />
                <isset property="output.exists" />
                <isset property="previous.digest" />
                <equals arg1="${current.digest}"
                        arg2="${previous.digest}"
                        trim="true" />
            </and>
        </condition>
    </target>

    <target name="generate" depends="check-inputs" unless="inputs.unchanged">
        <mkdir dir="${generated.dir}" />

        <copy file="${template.file}"
              tofile="${generated.file}"
              overwrite="true">
            <filterset>
                <filter token="APP_NAME" value="${app.name}" />
                <filter token="ENVIRONMENT" value="${environment}" />
            </filterset>
        </copy>

        <echo file="${state.file}" message="${current.digest}" />
        <echo message="Generated resources because one or more inputs changed." />
    </target>
</project>
```

Trong ví dụ, manifest `generation-options.txt` ghi các giá trị property ảnh hưởng đến đầu ra. Checksum tổng hợp tính trên template, cấu hình và manifest. Khi đổi `environment`, manifest đổi nội dung và fingerprint mới được tạo.

Lần đầu, state hoặc output chưa tồn tại nên target `generate` chạy. Các lần sau, nếu đầu vào và tùy chọn giống nhau, target được bỏ qua. Nếu nội dung template thay đổi nhưng timestamp bị giữ nguyên, digest tổng hợp vẫn đổi và tài nguyên được tạo lại.

## 14. Khi nào nên dùng checksum thay vì timestamp?

Checksum đặc biệt hữu ích trong những trường hợp:

- Đầu vào được đồng bộ từ nhiều máy và timestamp không nhất quán.
- Tệp được giải nén hoặc sao chép bằng công cụ giữ nguyên timestamp.
- Filesystem có độ phân giải timestamp thấp.
- Build cache được chia sẻ giữa môi trường khác nhau.
- Một bước tạo mã hoặc tài nguyên cần phát hiện thay đổi byte chính xác.
- Artifact tải từ repository cần được kiểm tra tính toàn vẹn.

Timestamp thường đủ khi:

- Source tree nằm trên filesystem cục bộ đáng tin cậy.
- Công cụ cập nhật timestamp đúng khi nội dung đổi.
- Chi phí đọc toàn bộ đầu vào lớn hơn lợi ích phát hiện thay đổi chính xác.
- Task của Ant đã có incremental behavior phù hợp và không có bằng chứng timestamp gây sai kết quả.

Không nên thêm checksum cho mọi tệp chỉ vì có thể. Hãy xác định điểm mà timestamp gây sai hoặc không đủ tin cậy, rồi dùng fingerprint cho đầu vào và target liên quan.

## 15. Bài thực hành

Tạo dự án:

```text
checksum-lab/
├── build.xml
├── src/
│   ├── config.properties
│   └── message.txt
└── build/
    ├── generated/
    └── state/
```

Viết buildfile với các yêu cầu:

1. Khai báo property cho tệp nguồn, thư mục output và tệp lưu digest.
2. Tạo target `check-input` dùng `<available>` để kiểm tra output và state.
3. Đọc digest cũ bằng `<loadfile failonerror="false">`.
4. Tính digest hiện tại bằng `<checksum algorithm="SHA-256" property="...">`.
5. Dùng `<condition>` để đặt property `input.unchanged` khi digest bằng nhau và output tồn tại.
6. Tạo target `generate` phụ thuộc `check-input`, dùng `unless="input.unchanged"`.
7. Tạo output bằng `<copy>` hoặc một bước xử lý tài nguyên.
8. Chỉ ghi digest mới sau khi output được tạo thành công.
9. Thử thay nội dung tệp nguồn nhưng khôi phục timestamp cũ.
10. Thử chỉ thay timestamp mà giữ nguyên byte nội dung.
11. Xóa output nhưng giữ state rồi chạy lại.
12. Xóa state nhưng giữ output rồi chạy lại.

Các lệnh kiểm tra có thể dùng:

```bash
ant generate
ant generate
ant -Denvironment=staging generate
```

Quan sát log để biết target tạo đầu ra có chạy hay không. Nếu muốn thử trường hợp timestamp không đổi nhưng nội dung đổi, dùng công cụ hoặc script có thể ghi nội dung mới rồi khôi phục thời gian sửa đổi của tệp. So sánh hành vi timestamp với hành vi checksum.

### Câu hỏi tự kiểm tra

1. Vì sao timestamp có thể không phản ánh thay đổi nội dung?
2. Checksum được tính từ dữ liệu nào?
3. Khác biệt giữa `<checksum property="...">` và `<checksum verifyproperty="...">` là gì?
4. Vì sao chỉ tính checksum mà không lưu digest chưa đủ cho incremental build qua nhiều lần chạy?
5. Vì sao phải kiểm tra output có tồn tại trước khi bỏ qua target?
6. `totalproperty` có ích gì khi task phụ thuộc nhiều tệp?
7. Ngoài mã nguồn, những thông tin nào có thể cần đưa vào fingerprint?
8. Vì sao phải ghi digest sau khi bước tạo output thành công?
9. `unless` của target kiểm tra giá trị `false` hay kiểm tra property đã tồn tại?
10. Checksum có thay thế chữ ký số khi xác minh nguồn gốc artifact không?
11. Vì sao checksum mọi tệp trong repository có thể làm build chậm?
12. Khi nào timestamp vẫn là lựa chọn phù hợp?

### Đáp án gợi ý

- Timestamp có thể được giữ nguyên, làm tròn theo độ phân giải filesystem hoặc lệch giữa các máy.
- Checksum được tính từ byte nội dung của tệp hoặc tập tệp được chọn.
- `property` lưu digest vừa tính; `verifyproperty` lưu kết quả xác minh nội dung so với checksum sidecar đã có.
- Property chỉ tồn tại trong lần chạy Ant hiện tại; cần lưu digest vào tệp hoặc cache bền vững để lần sau đọc lại.
- Nguồn không đổi nhưng output có thể đã bị xóa hoặc chưa được tạo.
- `totalproperty` tạo một fingerprint cho tập đầu vào được chọn thay vì quản lý từng digest riêng.
- Resource, cấu hình, compiler options, dependency version, annotation processor và phiên bản công cụ có thể ảnh hưởng kết quả.
- Nếu tạo output thất bại mà digest mới đã được lưu, lần sau build có thể bỏ qua một output chưa hợp lệ.
- `unless` kiểm tra property có được đặt hay không; giá trị chuỗi `false` vẫn được xem là đã tồn tại.
- Không. Checksum phát hiện thay đổi nội dung; chữ ký số hoặc provenance mới hỗ trợ xác thực nguồn phát hành.
- Vì checksum phải đọc toàn bộ byte, tạo chi phí I/O và CPU.
- Khi filesystem và công cụ cập nhật timestamp đáng tin cậy, kiểm tra timestamp nhanh và đủ cho task.

## Kết luận

Timestamp giúp Ant quyết định nhanh một bước build có thể cần chạy lại, nhưng timestamp không phải dấu vân tay nội dung. Khi tệp có thể thay đổi mà giữ nguyên thời gian sửa đổi, hoặc thời gian bị làm tròn hay lệch giữa các máy, hãy dùng checksum để so sánh byte đầu vào. Task `<checksum>` có thể ghi digest vào property, tạo checksum sidecar, xác minh sidecar hoặc tính fingerprint cho một tập tệp bằng `totalproperty`. Để incremental build hoạt động qua nhiều lần chạy, cần lưu digest cũ, đọc lại, so sánh với digest hiện tại, kiểm tra output còn tồn tại và chỉ cập nhật state sau khi tạo đầu ra thành công. Hãy đưa đầy đủ những đầu vào và tham số ảnh hưởng kết quả vào fingerprint, đồng thời cân nhắc chi phí đọc tệp trước khi áp dụng checksum trên diện rộng.
