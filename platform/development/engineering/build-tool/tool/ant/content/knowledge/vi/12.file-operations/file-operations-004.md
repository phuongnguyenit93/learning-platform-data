# Đồng bộ cây thư mục bằng sync và bảo vệ tệp cần giữ

Trong Apache Ant, task `<sync>` dùng để đồng bộ nội dung từ một hoặc nhiều tập nguồn vào một thư mục đích. Nó thực hiện hai nhóm công việc: sao chép các file được chọn từ nguồn sang đích theo quy tắc copy của Ant, sau đó loại khỏi thư mục đích những file không còn thuộc tập nội dung cần đồng bộ.

Điểm thứ hai khiến `sync` khác đáng kể với `<copy>`. Copy đưa file mới hoặc file cần cập nhật tới đích, nhưng không tự dọn những file cũ không còn trong nguồn. Sync có thể dọn phần dư để cây thư mục đích phản ánh tập file hiện tại của nguồn. Vì vậy, nếu thư mục đích có cấu hình theo môi trường, log, file upload hoặc dữ liệu do người vận hành tạo, cần khai báo rõ những file phải được giữ lại.

Task `<sync>` hỗ trợ nested element `<preserveintarget>` để mô tả các pattern của file trong thư mục đích cần bảo vệ khỏi bước xóa phần dư. Khi dùng đúng, build có thể cập nhật ứng dụng mà vẫn giữ cấu hình cục bộ hoặc dữ liệu vận hành cần thiết.

## 1. Phân biệt copy và sync

Giả sử thư mục build chứa phiên bản mới của ứng dụng:

~~~text
build/distribution/
├── app.jar
├── lib/
│   ├── core.jar
│   └── json.jar
└── config/
    └── application.properties
~~~

Thư mục triển khai hiện tại có thể chứa file cũ:

~~~text
deploy/app/
├── app.jar
├── lib/
│   ├── core.jar
│   ├── old-plugin.jar
│   └── json.jar
├── config/
│   ├── application.properties
│   └── local-overrides.properties
└── logs/
    └── previous-run.log
~~~

Nếu chỉ dùng `<copy>`, Ant có thể cập nhật `app.jar`, `core.jar`, `json.jar` và các file nguồn khác, nhưng `old-plugin.jar` vẫn còn ở đích vì copy không có nhiệm vụ xóa file không còn trong nguồn.

Nếu dùng `<sync>` với toàn bộ nội dung `build/distribution` làm nguồn, Ant sẽ cập nhật file nguồn và xóa các file đích không thuộc tập nguồn. Khi đó `old-plugin.jar`, `local-overrides.properties` và `previous-run.log` có thể bị xóa nếu không có quy tắc bảo vệ phù hợp.

| Đặc điểm | `<copy>` | `<sync>` |
|---|---|---|
| Sao chép file mới | Có | Có |
| Cập nhật file đích theo quy tắc copy | Có | Có |
| Xóa file đích không còn trong nguồn | Không | Có |
| Bảo vệ file đích được chỉ định | Không có cơ chế đồng bộ tương đương | Có thể dùng `<preserveintarget>` |
| Mục đích thường gặp | Bổ sung hoặc cập nhật file | Làm cho cây đích khớp với tập nguồn đã chọn |

Hãy dùng copy khi chỉ cần đưa thêm hoặc cập nhật file. Dùng sync khi muốn thư mục đích được quản lý như một bản phản chiếu của tập nguồn và đã xác định rõ dữ liệu nào cần được giữ lại.

## 2. Cú pháp cơ bản của `<sync>`

Ví dụ tối thiểu:

~~~xml
<property name="dist.dir" location="build/distribution"/>
<property name="deploy.dir" location="deploy/app"/>

<target name="sync-app">
    <sync todir="${deploy.dir}">
        <fileset dir="${dist.dir}"/>
    </sync>
</target>
~~~

Trong ví dụ:

- `todir` là thư mục đích cần đồng bộ.
- `<fileset dir="..."/>` xác định tập file nguồn.
- Ant sao chép các file thuộc FileSet sang thư mục đích.
- Các file hiện có trong thư mục đích nhưng không thuộc kết quả đồng bộ sẽ bị loại bỏ, trừ khi được bảo vệ.

Nếu FileSet không khai báo include hoặc exclude, tất cả file phù hợp bên dưới thư mục gốc của FileSet sẽ là ứng viên, ngoại trừ những file bị loại bởi default excludes. Khi dùng nhiều FileSet, tập nội dung được đồng bộ được hình thành từ các file nguồn mà các FileSet đó chọn.

`dir` và `todir` cần được xác định chính xác. Pattern trong FileSet được so khớp tương đối với `dir`; cấu trúc đường dẫn tương đối được duy trì khi file được đưa vào `todir`, trừ khi build cấu hình mapper thay đổi tên hoặc vị trí đầu ra.

## 3. Sync xóa những file nào ở đích?

Có thể hiểu quy tắc tổng quát của sync như sau:

~~~text
Tập file được chọn từ nguồn
          |
          v
Copy file mới hoặc file cần cập nhật
          |
          v
So sánh nội dung dự kiến với cây thư mục đích
          |
          v
Loại file đích không có trong tập nguồn
          |
          v
Giữ lại file đích được preserveintarget bảo vệ
~~~

Ví dụ, nguồn có:

~~~text
release/
├── app.jar
└── lib/
    └── core.jar
~~~

Đích ban đầu có:

~~~text
deploy/
├── app.jar
├── old-app.jar
├── lib/
│   ├── core.jar
│   └── unused.jar
└── temp/
    └── debug.txt
~~~

Sau khi đồng bộ toàn bộ FileSet nguồn, cây đích dự kiến còn:

~~~text
deploy/
├── app.jar
└── lib/
    └── core.jar
~~~

Các file `old-app.jar`, `lib/unused.jar` và `temp/debug.txt` không còn thuộc tập nguồn nên bị dọn. Đây là hành vi hữu ích khi triển khai phiên bản mới, vì file JAR cũ có thể gây xung đột classpath hoặc khiến ứng dụng nạp nhầm plugin.

Tuy nhiên, nếu thư mục đích còn chứa cấu hình theo môi trường hoặc dữ liệu do ứng dụng tạo ra, quy tắc này có thể gây mất dữ liệu. Không nên trỏ `todir` tới một thư mục dùng chung chưa được phân định rõ nội dung do build quản lý và nội dung cần giữ.

## 4. Bảo vệ file đích bằng `<preserveintarget>`

Nested element `<preserveintarget>` cho phép khai báo các pattern tương đối với thư mục đích để giữ lại file trong quá trình dọn phần dư.

Ví dụ:

~~~xml
<sync todir="${deploy.dir}">
    <fileset dir="${dist.dir}"/>

    <preserveintarget>
        <include name="config/local-overrides.properties"/>
        <include name="logs/**"/>
        <include name="uploads/**"/>
    </preserveintarget>
</sync>
~~~

Trong ví dụ, Ant vẫn đồng bộ các file thuộc nguồn. Khi dọn những file đích không có trong nguồn, các file khớp với pattern được khai báo trong `preserveintarget` sẽ được giữ lại.

Các pattern ở đây mô tả đường dẫn dưới `todir`, không phải đường dẫn dưới thư mục nguồn. Ví dụ `logs/**` bảo vệ nội dung dưới `deploy.dir/logs`; nó không có nghĩa là chọn thư mục `logs` từ source.

Có thể bảo vệ một file cụ thể:

~~~xml
<preserveintarget>
    <include name="config/application.properties"/>
</preserveintarget>
~~~

Hoặc bảo vệ cả một nhóm đường dẫn:

~~~xml
<preserveintarget>
    <include name="config/local/**"/>
    <include name="data/**"/>
</preserveintarget>
~~~

Chỉ nên bảo vệ những dữ liệu thực sự cần tồn tại qua các lần triển khai. Nếu đưa pattern quá rộng như `**`, gần như toàn bộ file đích có thể được giữ lại; các file cũ không còn thuộc release cũng sẽ không được dọn. Điều đó làm giảm ý nghĩa đồng bộ và có thể để lại thư viện hoặc class cũ gây lỗi.

## 5. Kết hợp include/exclude của nguồn với preserveintarget

`include` và `exclude` trong FileSet quyết định file nào thuộc tập nguồn. `preserveintarget` quyết định file nào trong đích được giữ lại khi dọn phần dư. Hai cơ chế có phạm vi khác nhau.

Ví dụ, gói phát hành có cấu hình mặc định:

~~~text
build/distribution/
├── app.jar
├── lib/
│   └── core.jar
└── config/
    └── application.properties
~~~

Mỗi máy triển khai có file cấu hình riêng tại `deploy/app/config/application.properties`. Muốn cập nhật ứng dụng nhưng giữ cấu hình local, cần loại file cấu hình mặc định khỏi tập nguồn đồng bộ và bảo vệ file đích tương ứng:

~~~xml
<sync todir="${deploy.dir}">
    <fileset dir="${dist.dir}">
        <exclude name="config/application.properties"/>
    </fileset>

    <preserveintarget>
        <include name="config/application.properties"/>
    </preserveintarget>
</sync>
~~~

Việc exclude cấu hình khỏi FileSet nguồn rất quan trọng. `preserveintarget` là cơ chế giữ file trong bước dọn phần dư; không nên xem nó như một chính sách merge hoặc một bảo đảm rằng file cùng đường dẫn trong nguồn sẽ không được copy đè. Nếu cấu hình local cần được giữ nguyên, hãy không đưa bản cấu hình mặc định vào tập file đồng bộ.

Kết quả mong muốn:

- `app.jar` và các thư viện được cập nhật từ release.
- File cấu hình local ở đích vẫn tồn tại.
- Những file đích khác không có trong release hoặc trong danh sách bảo vệ được dọn.

Nếu file cấu hình local không tồn tại ở lần triển khai đầu tiên, việc exclude file khỏi source có nghĩa sync không tự tạo file đó. Cần có bước cài đặt cấu hình mặc định riêng trước khi đồng bộ.

## 6. Cài cấu hình mặc định một lần rồi giữ cấu hình local

Một mẫu thường gặp là: lần đầu triển khai, copy file cấu hình mẫu nếu đích chưa có; các lần sau, giữ cấu hình local và không copy đè nó.

~~~xml
<property name="dist.dir" location="build/distribution"/>
<property name="deploy.dir" location="deploy/app"/>
<property name="local.config" location="${deploy.dir}/config/application.properties"/>

<target name="check-local-config">
    <available file="${local.config}" property="local.config.exists"/>
</target>

<target name="install-default-config"
        depends="check-local-config"
        unless="local.config.exists">
    <copy file="${dist.dir}/config/application.properties"
          todir="${deploy.dir}/config"/>
</target>

<target name="deploy" depends="install-default-config">
    <sync todir="${deploy.dir}">
        <fileset dir="${dist.dir}">
            <exclude name="config/application.properties"/>
        </fileset>
        <preserveintarget>
            <include name="config/application.properties"/>
            <include name="logs/**"/>
        </preserveintarget>
    </sync>
</target>
~~~

Luồng chạy:

1. `check-local-config` kiểm tra file cấu hình ở thư mục đích bằng `<available>`.
2. Nếu file chưa tồn tại, `install-default-config` chạy và copy cấu hình mặc định từ release.
3. Nếu file đã tồn tại, property `local.config.exists` được đặt; do `unless`, phần copy mặc định bị bỏ qua.
4. `deploy` chạy sau bước cài đặt cấu hình.
5. Sync loại file cấu hình khỏi tập nguồn và bảo vệ đường dẫn cấu hình ở đích, nên cấu hình local được giữ qua các lần đồng bộ.
6. Nội dung `logs/**` ở đích cũng được giữ, kể cả khi release không chứa các file log đó.

Mẫu này dựa trên quy tắc property tồn tại của Ant: `unless="local.config.exists"` kiểm tra property có được đặt hay không. Giá trị `false` dạng chuỗi vẫn được xem là property đã tồn tại, nên không dùng cách đặt `local.config.exists=false` để biểu diễn file không tồn tại.

Trong môi trường thực tế, có thể cần tạo thư mục cấu hình trước, kiểm tra quyền ghi và xác định cách backup file local trước khi triển khai. Ví dụ trên giả định file cấu hình mặc định có trong `${dist.dir}` và thư mục cha có thể được tạo bởi task copy.

## 7. Nhiều FileSet nguồn trong một lần sync

Một thư mục triển khai có thể được tạo từ nhiều nguồn khác nhau, ví dụ artifact chính, tài nguyên tĩnh và file script vận hành:

~~~xml
<sync todir="${deploy.dir}">
    <fileset dir="build/classes">
        <include name="**/*.class"/>
    </fileset>

    <fileset dir="src/main/resources">
        <include name="**/*"/>
        <exclude name="local/**"/>
    </fileset>

    <fileset dir="distribution/scripts">
        <include name="**/*.sh"/>
        <include name="**/*.ps1"/>
    </fileset>

    <preserveintarget>
        <include name="config/local/**"/>
        <include name="logs/**"/>
    </preserveintarget>
</sync>
~~~

Các FileSet tạo thành tập nội dung nguồn của lần đồng bộ. File ở đích không thuộc tập kết quả của bất kỳ FileSet nào sẽ được xem là phần dư và có thể bị xóa, trừ khi được bảo vệ.

Khi dùng nhiều FileSet, hãy kiểm tra chúng có tạo ra các đường dẫn đích trùng nhau hay không. Nếu hai nguồn cùng đưa một file đến cùng một đường dẫn, kết quả phụ thuộc vào thứ tự và quy tắc copy; đây thường là cấu hình khó hiểu và nên được tránh bằng cách phân vùng đường dẫn rõ ràng.

Cũng cần cẩn thận với exclude. Khi loại một file khỏi FileSet, file tương ứng ở đích không còn được xem là thành phần của tập nguồn. Nếu muốn file đó vẫn tồn tại ở đích, phải bảo vệ bằng `preserveintarget` hoặc đặt nó ngoài cây thư mục do sync quản lý.

## 8. Quy tắc copy và thuộc tính liên quan

`<sync>` dùng cơ chế sao chép của Ant cho những file được chọn. Vì vậy, các quy tắc copy vẫn có ý nghĩa:

- File chưa tồn tại ở đích sẽ được tạo.
- File nguồn mới hơn file đích thường được copy để cập nhật.
- Có thể dùng `overwrite="true"` khi cần ép copy các file được chọn, kể cả khi timestamp cho thấy file đích mới hơn.
- Các thuộc tính copy như filtering hoặc mapper có thể ảnh hưởng nội dung hoặc vị trí file đầu ra nếu task và cấu hình hỗ trợ.

Ví dụ ép cập nhật các file nguồn được chọn:

~~~xml
<sync todir="${deploy.dir}" overwrite="true">
    <fileset dir="${dist.dir}"/>
</sync>
~~~

`overwrite="true"` không có nghĩa là bảo vệ file local. Nó buộc các file nguồn được chọn được copy đè theo cấu hình copy. Nếu một file cấu hình local có cùng đường dẫn với file nguồn và không được exclude, nó vẫn có thể bị thay thế. Hãy loại file local khỏi tập nguồn và dùng `preserveintarget` cho bước dọn phần dư.

Đừng nhầm `overwrite` với việc xóa file thừa. `overwrite` quyết định việc copy file đã tồn tại ở đích; hành vi dọn file không thuộc nguồn là đặc trưng của sync.

## 9. Bảo vệ dữ liệu theo kiến trúc thư mục

Cách an toàn nhất thường là tách nội dung do build quản lý khỏi nội dung do môi trường vận hành quản lý.

Ví dụ:

~~~text
deploy/app/
├── app/                 # Nội dung do release đồng bộ
│   ├── app.jar
│   └── lib/
├── config/              # Cấu hình theo môi trường
│   └── application.properties
├── data/                # Dữ liệu do ứng dụng hoặc vận hành tạo
└── logs/                # Log runtime
~~~

Có thể chỉ sync vào `deploy/app/app`, còn `config`, `data` và `logs` nằm ngoài `todir`. Khi đó sync không có quyền dọn những khu vực đó vì chúng không nằm trong cây đích của task.

Nếu vì lý do tương thích cần đặt cấu hình và dữ liệu dưới cùng thư mục đích, hãy khai báo pattern bảo vệ thật cụ thể:

~~~xml
<preserveintarget>
    <include name="config/application.properties"/>
    <include name="config/secrets/**"/>
    <include name="data/**"/>
    <include name="logs/**"/>
</preserveintarget>
~~~

Không nên bảo vệ toàn bộ `config/**` nếu release cần cập nhật một số file cấu hình dùng chung trong thư mục đó. Hãy liệt kê đúng file local cần giữ, hoặc chia thư mục thành `config/defaults` do release quản lý và `config/local` do môi trường quản lý.

## 10. Rủi ro và biện pháp triển khai an toàn

Sync có thể xóa file đích, vì vậy cần xác định rõ phạm vi trước khi chạy trên môi trường quan trọng.

### 10.1. Chọn đúng thư mục đích

Không đặt `todir` là thư mục gốc repository, thư mục home hoặc thư mục dùng chung chứa dữ liệu ngoài ứng dụng. Nên đồng bộ vào một thư mục staging/deploy dành riêng cho ứng dụng.

### 10.2. Kiểm tra nguồn trước khi sync

Nếu source directory rỗng do build trước đó thất bại hoặc sai đường dẫn, sync có thể khiến thư mục đích bị dọn mạnh hơn dự kiến. Trước khi đồng bộ, bảo đảm target build đã tạo artifact và source directory đúng.

~~~xml
<target name="verify-distribution">
    <available file="${dist.dir}/app.jar"
               property="distribution.ready"/>
    <fail unless="distribution.ready"
          message="Distribution is missing app.jar; refusing to sync."/>
</target>

<target name="deploy" depends="verify-distribution">
    <sync todir="${deploy.dir}">
        <fileset dir="${dist.dir}"/>
    </sync>
</target>
~~~

Target `verify-distribution` đặt property nếu artifact chính tồn tại; task `<fail>` dừng build nếu không có artifact. `deploy` chỉ được thực hiện sau khi kiểm tra thành công. Trong dự án thực tế, có thể kiểm tra thêm các thư viện, manifest hoặc file bắt buộc khác.

### 10.3. Thử trên staging trước

Trước khi chạy sync trên production, hãy đồng bộ vào một thư mục staging có cấu trúc tương tự. Kiểm tra file được copy, file bị xóa và file được giữ lại. Sau khi kết quả đúng mới áp dụng cùng cấu hình lên đích chính thức.

### 10.4. Backup cấu hình và dữ liệu local

Các file được preserve vẫn có thể bị mất do lỗi khác, thao tác thủ công hoặc thay đổi pattern. Cấu hình quan trọng và dữ liệu vận hành cần có chính sách backup riêng. `preserveintarget` không phải hệ thống backup và không cung cấp lịch sử phiên bản.

### 10.5. Tách đồng bộ khỏi restart hoặc deploy service

Sync chỉ cập nhật cây file. Nó không tự bảo đảm ứng dụng đã nạp cấu hình mới, restart service, kiểm tra health hoặc rollback. Hãy tách các bước đồng bộ, kiểm tra, phê duyệt, restart và xác minh sau triển khai thành các target hoặc stage rõ ràng.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| File cũ vẫn còn ở đích | Đang dùng `<copy>` thay vì `<sync>`, hoặc file được preserve | Kiểm tra task và pattern `preserveintarget` |
| File local bị xóa sau deploy | File không có trong source và chưa được preserve | Thêm pattern bảo vệ hoặc chuyển dữ liệu ra ngoài `todir` |
| Cấu hình local bị ghi đè | File cấu hình vẫn được chọn trong FileSet nguồn | Exclude file đó khỏi source; preserveintarget chỉ xử lý việc giữ file đích khi dọn |
| File mới không xuất hiện | Source FileSet không chọn file hoặc sai `dir` | In/kiểm tra base directory và include pattern |
| Thư viện cũ vẫn tồn tại | Pattern preserve quá rộng hoặc file vẫn được chọn từ một FileSet khác | Thu hẹp preserve và rà soát toàn bộ tập nguồn |
| Nhiều file cùng ghi vào một đường dẫn | Các FileSet hoặc mapper chồng lấn | Phân chia destination path rõ ràng |
| Đích bị dọn gần như toàn bộ | Source sai hoặc rỗng, `todir` trỏ nhầm nơi | Kiểm tra artifact và đường dẫn; thêm target verify trước sync |
| File không được copy dù source thay đổi | Quy tắc timestamp của copy không kích hoạt | Kiểm tra Last Modified hoặc cân nhắc `overwrite="true"` |
| Cấu hình mặc định không được tạo lần đầu | File đã bị exclude nhưng chưa có bước cài đặt ban đầu | Thêm target kiểm tra và copy default nếu đích chưa tồn tại |

## 12. Quy trình thiết kế một target sync

Khi xây dựng target đồng bộ, hãy xác định lần lượt:

1. Thư mục nguồn nào tạo nên bản phát hành?
2. FileSet nào được chọn và file nào bị exclude?
3. `todir` là thư mục riêng do build quản lý hay có chứa dữ liệu khác?
4. File nào phải được giữ lại dù không còn trong source?
5. File local có bị trùng đường dẫn với file nguồn không? Nếu có, cần exclude khỏi source để tránh copy đè.
6. Cần cài cấu hình mặc định ở lần đầu hay không?
7. Có kiểm tra artifact bắt buộc trước sync không?
8. Có staging, backup và bước xác minh sau sync không?

Một luồng triển khai có thể được tổ chức như sau:

~~~text
compile / package
       |
       v
verify distribution
       |
       v
install default config if missing
       |
       v
sync release files
       |
       v
preserve local config and runtime data
       |
       v
verify deployed tree
       |
       v
restart / health check (nếu pipeline yêu cầu)
~~~

Mỗi bước nên có target riêng nếu cần gọi hoặc kiểm tra độc lập. `depends` thể hiện thứ tự bắt buộc giữa các target; `<sync>` đảm nhiệm việc cập nhật và dọn cây file; `<preserveintarget>` mô tả những file đích không được xóa trong quá trình dọn.

## Kết luận

`<sync>` đồng bộ tập file được chọn từ nguồn sang thư mục đích và loại bỏ file đích không còn thuộc tập nguồn. Đây là cách hữu ích để triển khai release sạch, nhưng có thể xóa cấu hình hoặc dữ liệu local nếu chúng không được bảo vệ. Dùng `<preserveintarget>` với pattern tương đối dưới `todir` để giữ file đích cần thiết; đồng thời exclude file cấu hình local khỏi FileSet nguồn nếu không muốn bản release copy đè nó. Luôn chọn thư mục đích chuyên biệt, xác minh nguồn trước khi sync, thử trên staging và backup dữ liệu quan trọng trước khi áp dụng vào môi trường vận hành.