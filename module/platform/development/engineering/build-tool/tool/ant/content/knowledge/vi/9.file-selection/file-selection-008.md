# Chọn tệp theo nội dung hoặc trạng thái thay đổi

Trong Apache Ant, `fileset` thường được dùng để chọn file theo đường dẫn và tên file thông qua `include` và `exclude`. Khi cần lọc sâu hơn, Ant cung cấp **file selectors**: các bộ chọn có thể kiểm tra nội dung, thời điểm sửa đổi, kích thước hoặc sự khác biệt giữa file nguồn với một bản tham chiếu.

Nhờ selectors, một target có thể chỉ xử lý những file thực sự cần thiết. Ví dụ, ta có thể copy các file cấu hình chứa token cần rà soát, chọn file mới hơn bản đã phát hành hoặc chỉ đóng gói những file có nội dung thay đổi.

## 1. Fileset và selector phối hợp với nhau

`fileset` xác định thư mục gốc và tập file ứng viên. Các mẫu `include` và `exclude` lọc theo đường dẫn tương đối; selectors tiếp tục kiểm tra từng file ứng viên theo điều kiện cụ thể.

```xml
<fileset dir="src">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
    <contains text="TODO" casesensitive="true"/>
</fileset>
```

Đọc cấu hình theo thứ tự ý nghĩa:

1. Bắt đầu từ thư mục `src`.
2. Chỉ xét các file Java ở mọi cấp thư mục.
3. Loại các file nằm trong cây thư mục `generated`.
4. Trong số file còn lại, chỉ chọn file có nội dung chứa chuỗi `TODO`.

Như vậy, `include` và `exclude` chọn theo tên/đường dẫn, còn `<contains>` chọn theo nội dung file. Nếu có nhiều selector độc lập trong một fileset, các điều kiện selector được kết hợp theo AND; dùng selector container như `<or>` hoặc `<not>` khi muốn biểu diễn logic khác.

Selector không tự copy, xóa hay đóng gói file. Nó chỉ quyết định file nào được đưa vào tập tài nguyên mà task đang xử lý. Task như `<copy>`, `<delete>`, `<jar>` hoặc `<zip>` mới thực hiện hành động.

## 2. Chọn file theo nội dung bằng contains

`<contains>` chọn file có chứa một chuỗi văn bản. Đây là lựa chọn phù hợp khi muốn tìm các file có marker, TODO, tên thuộc tính hoặc một đoạn cấu hình cụ thể.

```xml
<fileset dir="src/main">
    <include name="**/*.java"/>
    <contains text="TODO" casesensitive="true"/>
</fileset>
```

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `text` | Chuỗi cần tìm trong nội dung file |
| `casesensitive` | Có phân biệt chữ hoa/chữ thường hay không; mặc định là phân biệt |
| `ignorewhitespace` | Có bỏ qua khác biệt về khoảng trắng khi so sánh hay không |

Ví dụ trên chọn file có chuỗi `TODO` đúng kiểu chữ. Nếu đặt `casesensitive="false"`, các cách viết `TODO`, `Todo` hoặc `todo` đều có thể khớp.

Có thể dùng selector trong một task:

```xml
<target name="collect-todo-files">
    <copy todir="build/review">
        <fileset dir="src/main/java">
            <include name="**/*.java"/>
            <contains text="TODO" casesensitive="false"/>
        </fileset>
    </copy>
</target>
```

Khi chạy `ant collect-todo-files`, Ant copy các file Java có chứa marker TODO vào `build/review`, giữ cấu trúc thư mục tương đối của tập nguồn.

`contains` đọc nội dung file, vì vậy nên áp dụng cho file văn bản có encoding phù hợp. Không dùng nó để lọc ảnh, JAR hoặc file nhị phân. Với file rất lớn hoặc số lượng file nhiều, việc đọc nội dung để kiểm tra có thể tốn thời gian hơn lọc tên file.

## 3. Chọn file theo thời điểm sửa đổi bằng date

`<date>` chọn file dựa trên thời điểm sửa đổi cuối cùng (last modified time). Selector này hữu ích khi muốn xử lý file được cập nhật sau một mốc thời gian, hoặc giới hạn một đợt rà soát theo ngày.

```xml
<fileset dir="src/main/resources">
    <include name="**/*"/>
    <date datetime="01/01/2025 00:00 AM" when="after"/>
</fileset>
```

Thuộc tính `datetime` xác định mốc thời gian để so sánh. `when` cho biết quan hệ cần chọn, thường là `before`, `after` hoặc `equal`. Ant hỗ trợ thêm `granularity` để tính đến độ chính xác timestamp của hệ thống file; điều này hữu ích khi so sánh file giữa các hệ điều hành hoặc môi trường có độ phân giải thời gian khác nhau.

Ví dụ chọn file được sửa trước một mốc:

```xml
<fileset dir="incoming">
    <include name="**/*.csv"/>
    <date datetime="01/01/2025 00:00 AM" when="before"/>
</fileset>
```

`date` chỉ xét timestamp của file. Nó không đọc nội dung để xác định thay đổi thực sự. Nếu một file được chạm timestamp nhưng nội dung không đổi, selector vẫn có thể xem nó là file mới hơn mốc thời gian. Ngược lại, nếu nội dung đổi nhưng timestamp được giữ nguyên, selector có thể không nhận ra.

Định dạng chuỗi ngày giờ cần phù hợp với quy tắc parse của Ant. Trong môi trường build nhiều vùng địa phương, nên thống nhất định dạng và timezone của mốc thời gian để kết quả không phụ thuộc cấu hình máy.

## 4. Chọn file theo kích thước bằng size

`<size>` chọn file dựa trên dung lượng. Selector này hữu ích khi cần tìm file lớn, bỏ qua file rỗng hoặc giới hạn đầu vào của một bước xử lý.

```xml
<fileset dir="uploads">
    <include name="**/*"/>
    <size value="10" units="M" when="more"/>
</fileset>
```

Ví dụ chọn các file có kích thước lớn hơn 10 MB theo đơn vị mà selector hỗ trợ. Các thuộc tính chính:

- `value`: ngưỡng kích thước.
- `units`: đơn vị như byte, kilobyte, megabyte hoặc đơn vị lớn hơn theo hỗ trợ của Ant.
- `when`: chọn file có kích thước `less`, `equal` hoặc `more` so với ngưỡng.

Kích thước file là metadata, không phản ánh nội dung có thay đổi hay không. Một file có thể giữ nguyên dung lượng nhưng nội dung đã đổi; ngược lại, file có thể lớn hơn mà không liên quan đến việc nó mới được sửa.

## 5. Chọn file mới hơn bản tương ứng bằng depend

`<depend>` so sánh file trong fileset nguồn với file tương ứng trong một thư mục đích. Selector chọn file nguồn khi file tương ứng không tồn tại hoặc file nguồn mới hơn file đích theo timestamp, có tính đến `granularity`.

```xml
<fileset dir="src/resources">
    <include name="**/*"/>
    <depend targetdir="build/resources"/>
</fileset>
```

Giả sử hai thư mục có cùng cấu trúc tương đối:

```text
src/resources/
├── app.properties
└── messages.properties

build/resources/
├── app.properties
└── messages.properties
```

Nếu `app.properties` trong source mới hơn bản tương ứng trong `build/resources`, file nguồn được chọn. Nếu `messages.properties` không thay đổi và bản đích đã tồn tại với timestamp mới hơn hoặc bằng theo độ phân giải được xét, file đó không được chọn.

`depend` hữu ích trong các bước copy tài nguyên tăng dần:

```xml
<target name="copy-changed-resources">
    <copy todir="build/resources">
        <fileset dir="src/resources">
            <include name="**/*"/>
            <depend targetdir="build/resources"/>
        </fileset>
    </copy>
</target>
```

Task copy chỉ nhận các file được selector chọn. Các file nguồn mới hoặc mới hơn bản đích sẽ được sao chép. Hãy bảo đảm cấu trúc đường dẫn nguồn và đích tương ứng; nếu tên file được đổi trong quá trình build, cần cấu hình mapper phù hợp cho task và kiểm tra khả năng ánh xạ tương ứng của selector.

Vì `depend` dựa vào thời gian sửa đổi, nó không phải phép so sánh nội dung. Nếu cần xác định nội dung khác nhau ngay cả khi timestamp không phản ánh thay đổi, hãy xem selector `different`.

## 6. Chọn file khác nội dung với bản tham chiếu bằng different

`<different>` chọn file khi file tương ứng trong một thư mục khác không giống file nguồn. Nó phù hợp khi cần đồng bộ nội dung hoặc chỉ copy những file khác với một bản baseline.

```xml
<fileset dir="src/config">
    <include name="**/*.properties"/>
    <different targetdir="release/config" ignoreFileTimes="true"/>
</fileset>
```

`targetdir` là thư mục chứa các file dùng làm bản tham chiếu. `ignoreFileTimes="true"` yêu cầu bỏ qua khác biệt về timestamp để tập trung vào nội dung file. Khi đó, file có timestamp khác nhưng byte nội dung giống nhau không bị xem là khác chỉ vì thời gian sửa đổi.

Ví dụ:

```text
src/config/app.properties       Nội dung: mode=prod
release/config/app.properties   Nội dung: mode=dev
```

File nguồn được chọn vì nội dung khác với file tương ứng trong `release/config`. Nếu hai file có cùng nội dung, selector không cần chọn file chỉ vì timestamp khác khi `ignoreFileTimes` bật.

Có thể dùng selector này với task copy:

```xml
<target name="sync-config">
    <copy todir="release/config">
        <fileset dir="src/config">
            <include name="**/*.properties"/>
            <different targetdir="release/config" ignoreFileTimes="true"/>
        </fileset>
    </copy>
</target>
```

Nếu file tương ứng trong target chưa tồn tại, file nguồn được xem là khác và được chọn để copy. `different` có thể phải đọc/so sánh nội dung, do đó chi phí có thể cao hơn kiểm tra timestamp. Chọn selector theo yêu cầu chính xác của bước build.

## 7. Chọn file đã thay đổi kể từ lần chạy trước bằng modified

`<modified>` là selector dành cho trường hợp cần biết file có thay đổi so với lần kiểm tra trước hay không. Nó sử dụng cache để lưu dấu vết của file, chẳng hạn thông tin checksum hoặc digest, rồi so sánh ở lần chạy sau.

```xml
<fileset dir="src/main/resources">
    <include name="**/*"/>
    <modified/>
</fileset>
```

Khi lần đầu chưa có cache, Ant chưa có baseline để so sánh nên các file mới được ghi nhận như dữ liệu ban đầu. Ở các lần chạy sau, selector có thể nhận ra file đã thay đổi so với thông tin đã lưu.

Với build thực tế, cần chú ý cấu hình cache của modified selector. Cache nên nằm ở vị trí ổn định giữa các lần chạy nếu mục tiêu là phát hiện thay đổi xuyên suốt nhiều lần build. Không đặt cache trong thư mục output bị `clean` xóa nếu muốn giữ lịch sử. Ngược lại, nếu cache được tạo lại từ đầu mỗi lần chạy, selector sẽ mất khả năng so sánh với lần trước.

Ví dụ cấu hình cache file riêng thông qua tham số của selector:

```xml
<fileset dir="src/main/resources">
    <include name="**/*"/>
    <modified>
        <param name="cache.cachefile" value="${basedir}/.ant/modified-cache.properties"/>
    </modified>
</fileset>
```

Thư mục `.ant` cần tồn tại hoặc được chuẩn bị trước nếu cấu hình cache yêu cầu đường dẫn cha có sẵn. Hãy chọn cache riêng cho mỗi dự án hoặc tập dữ liệu, tránh để nhiều build độc lập ghi đè cùng một file cache.

`modified` khác `different` ở baseline so sánh:

- `different` so sánh file hiện tại với file tương ứng trong một thư mục tham chiếu.
- `modified` so sánh file hiện tại với dấu vết đã lưu trong cache từ lần kiểm tra trước.
- `depend` so sánh timestamp của file nguồn với file tương ứng trong thư mục đích.

Vì cache là một phần trạng thái của build, hãy bảo vệ nó khỏi ghi đồng thời từ nhiều tiến trình và cân nhắc cách lưu cache trong CI nếu các job chạy trên máy tạm thời.

## 8. Kết hợp selector bằng and, or và not

Khi một file phải thỏa nhiều điều kiện hoặc chỉ cần thỏa một trong nhiều điều kiện, dùng selector container để biểu diễn logic rõ ràng.

### 8.1. AND: tất cả điều kiện đều phải đúng

Ví dụ chọn file Java vừa chứa `TODO`, vừa được sửa sau một mốc thời gian:

```xml
<fileset dir="src/main/java">
    <include name="**/*.java"/>
    <and>
        <contains text="TODO" casesensitive="false"/>
        <date datetime="01/01/2025 00:00 AM" when="after"/>
    </and>
</fileset>
```

Chỉ file thỏa cả hai điều kiện mới được chọn. Nếu file chứa TODO nhưng cũ hơn mốc ngày, file không được chọn.

### 8.2. OR: chỉ cần một điều kiện đúng

Ví dụ chọn file có chứa marker `TODO` hoặc `FIXME`:

```xml
<fileset dir="src">
    <include name="**/*.java"/>
    <or>
        <contains text="TODO" casesensitive="false"/>
        <contains text="FIXME" casesensitive="false"/>
    </or>
</fileset>
```

File có một trong hai marker đều được chọn. Nếu một file chứa cả hai marker, nó vẫn chỉ là một phần tử của tập tài nguyên.

### 8.3. NOT: đảo ngược kết quả của một selector

Ví dụ chọn file cấu hình không chứa token `LOCAL_ONLY`:

```xml
<fileset dir="config">
    <include name="**/*.properties"/>
    <not>
        <contains text="LOCAL_ONLY"/>
    </not>
</fileset>
```

`<not>` nhận một selector con và đảo kết quả của selector đó. Hãy dùng dấu ngoặc logic bằng các container khi biểu thức có nhiều điều kiện, để người đọc không phải suy luận cách kết hợp từ nhiều phần tử XML rời rạc.

## 9. Phân biệt các selector theo trạng thái thay đổi

Các selector sau có mục đích gần nhau nhưng dùng loại thông tin khác nhau:

| Selector | Dữ liệu so sánh | Chọn file khi |
|---|---|---|
| `date` | Timestamp của file và một mốc thời gian | File trước/sau/đúng mốc theo `when` |
| `depend` | Timestamp file nguồn và file tương ứng trong `targetdir` | File nguồn mới hơn hoặc file đích chưa có |
| `different` | File nguồn và file tương ứng trong `targetdir` | Hai file khác nhau theo cấu hình so sánh |
| `modified` | Nội dung/dấu vết file và cache từ lần trước | File thay đổi so với trạng thái đã lưu |
| `size` | Kích thước file và một ngưỡng | Kích thước nhỏ hơn, bằng hoặc lớn hơn ngưỡng |
| `contains` | Nội dung file và chuỗi cần tìm | File chứa chuỗi được chỉ định |

Chọn selector theo câu hỏi cần trả lời:

- “File có chứa chuỗi này không?” → `contains`.
- “File được sửa sau ngày nào?” → `date`.
- “File nguồn mới hơn bản đích không?” → `depend`.
- “Nội dung file có khác bản phát hành không?” → `different`.
- “File có đổi kể từ lần build trước không?” → `modified`.
- “File có lớn hơn một ngưỡng không?” → `size`.

Không nên thay thế mọi phép kiểm tra bằng `date`. Timestamp có thể bị thay đổi khi copy, checkout từ version control hoặc giải nén archive. Nếu yêu cầu là so sánh nội dung, hãy dùng selector có cơ chế so sánh nội dung hoặc checksum.

## 10. Một ví dụ tổng hợp: copy file cấu hình cần cập nhật

Giả sử dự án có cấu trúc:

```text
project/
├── build.xml
├── src/main/resources/
│   ├── app.properties
│   ├── database.properties
│   └── local.properties
├── release/config/
└── build/review/
```

Ta muốn copy các file properties có nội dung chứa `endpoint=`, bỏ file local và chỉ copy khi khác bản phát hành:

```xml
<project name="config-sync" default="sync-config" basedir=".">
    <property name="source.config" location="${basedir}/src/main/resources"/>
    <property name="release.config" location="${basedir}/release/config"/>

    <target name="init">
        <mkdir dir="${release.config}"/>
        <mkdir dir="${basedir}/build/review"/>
    </target>

    <target name="sync-config" depends="init">
        <copy todir="${release.config}">
            <fileset dir="${source.config}">
                <include name="**/*.properties"/>
                <exclude name="**/local.properties"/>
                <contains text="endpoint=" casesensitive="false"/>
                <different targetdir="${release.config}" ignoreFileTimes="true"/>
            </fileset>
        </copy>
    </target>
</project>
```

Trong ví dụ, fileset giới hạn đầu vào theo tên, loại file local, kiểm tra nội dung và so sánh với bản phát hành. Chỉ file vừa có `endpoint=` vừa khác file tương ứng trong `release/config` mới được copy.

Nếu file cấu hình không tồn tại trong `release/config`, selector `different` coi nó là file cần đưa vào. Nếu file có nội dung giống nhau, selector không chọn nó dù timestamp khác vì `ignoreFileTimes` đang bật.

Lưu ý: target `init` tạo thư mục release trước khi copy. Nếu build có bước khác xóa thư mục release, cần bảo đảm bước đó không chạy sau `init` và trước khi selector so sánh.

## 11. Lưu ý về hiệu năng và tính ổn định

Selector càng cần đọc hoặc so sánh nhiều dữ liệu thì chi phí chọn file càng lớn. Lọc theo tên bằng `include`/`exclude` thường rẻ hơn đọc nội dung bằng `contains` hoặc so sánh nội dung bằng `different`.

Một số nguyên tắc thực tế:

1. Thu hẹp tập ứng viên bằng `include` và `exclude` trước khi áp dụng selector đọc nội dung.
2. Chọn `depend` khi chỉ cần kiểm tra file nguồn có mới hơn output tương ứng theo timestamp hay không.
3. Chọn `different` khi yêu cầu so sánh nội dung với thư mục tham chiếu.
4. Chọn `modified` khi cần theo dõi thay đổi qua nhiều lần chạy và có thể duy trì cache.
5. Đặt cache ở vị trí có vòng đời phù hợp; không để `clean` xóa cache nếu cần so sánh xuyên các lần build.
6. Tránh cho nhiều build đồng thời ghi chung một cache file nếu cơ chế cache không được thiết kế cho truy cập đồng thời.
7. Thử selector với một tập file nhỏ và quan sát danh sách được chọn trước khi dùng nó cho thao tác xóa hoặc phát hành.

Với thao tác có tính phá hủy như `<delete>`, nên bắt đầu bằng cách dùng cùng fileset cho một task chỉ in danh sách file hoặc copy sang thư mục tạm để xác nhận phạm vi. Chỉ đưa selector vào bước xóa khi đã hiểu chính xác tập file mà nó chọn.

## 12. Bài tập thực hành

1. Tạo thư mục `src/messages` chứa một số file `.properties`, trong đó chỉ một vài file có chuỗi `TODO`.
2. Dùng `contains` để copy riêng các file có TODO sang `build/review`.
3. Thêm `date` để chỉ chọn file được sửa sau một mốc đã cho.
4. Tạo bản sao thư mục `release/messages`, thay đổi nội dung một file và dùng `different` để chọn file khác biệt.
5. Dùng `depend` để chỉ chọn file nguồn mới hơn bản đích.
6. Dùng `modified` với cache để chạy hai lần: lần đầu tạo baseline, lần sau sửa một file rồi quan sát kết quả chọn.
7. Kết hợp `contains` và `date` trong `<and>`, sau đó đổi sang `<or>` và so sánh tập file.
8. Viết một target copy các file đã chọn và giải thích selector nào kiểm tra tên, selector nào kiểm tra nội dung, selector nào so sánh trạng thái.

Khi hoàn thành, người học cần chọn được đúng selector cho từng nhu cầu và hiểu rằng selector chỉ lọc tập file đầu vào. Task vẫn là thành phần thực hiện copy, đóng gói, xóa hoặc xử lý các file được chọn.
