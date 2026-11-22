# `union`, `intersect` và `difference` giữa các tập tài nguyên trong Apache Ant

Apache Ant có nhiều data type biểu diễn một tập tài nguyên (ResourceCollection), chẳng hạn `fileset`, `filelist` và `path`. Khi buildfile cần kết hợp tài nguyên từ nhiều nguồn, chọn phần giao nhau hoặc loại bỏ một nhóm tài nguyên khỏi tập ban đầu, có thể dùng ba resource collection: `union`, `intersect` và `difference`.

Ba phép toán này giúp mô tả tập đầu vào ngay trong buildfile. Thay vì tạo nhiều target trung gian hoặc lặp lại danh sách file, ta có thể kết hợp các collection thành một collection mới rồi đưa nó vào task hỗ trợ ResourceCollection, ví dụ `copy`.

## 1. ResourceCollection là gì?

ResourceCollection là một tập hợp tài nguyên mà task Ant có thể duyệt qua. Mỗi phần tử là một `Resource`, có thể là file trên filesystem, một mục trong danh sách file hoặc tài nguyên được cung cấp bởi một data type khác. Một số collection thường gặp:

| Data type | Vai trò |
|---|---|
| `fileset` | Chọn các file trong một thư mục theo include/exclude và selector |
| `filelist` | Liệt kê tường minh các file cần dùng |
| `path` | Tập hợp các phần tử đường dẫn như thư mục hoặc JAR |
| `zipfileset` | Chọn tài nguyên bên trong một archive ZIP |
| `union` | Kết hợp các ResourceCollection thành hợp |
| `intersect` | Lấy tài nguyên xuất hiện trong tất cả collection đầu vào |
| `difference` | Lấy tài nguyên của collection đầu tiên sau khi loại các tài nguyên thuộc những collection tiếp theo |

Ví dụ, một project có thể có tài nguyên được viết thủ công trong `src/main/resources`, tài nguyên được sinh ra trong `build/generated-resources`, và các file mẫu chỉ dùng trong phát triển. Những nhóm này có thể được biểu diễn thành các `fileset` riêng, sau đó kết hợp theo nhu cầu của từng task.

## 2. Phép hợp với `union`

`union` trả về tập tài nguyên thuộc ít nhất một trong các ResourceCollection con. Nếu cùng một resource xuất hiện trong nhiều collection đầu vào, `union` loại bỏ phần tử trùng theo cách so sánh/equality của Resource.

Về mặt tập hợp, nếu có hai collection A và B:

\[A \cup B = \{x \mid x \in A \text{ hoặc } x \in B\}\]

Ví dụ, gom tài nguyên chính và tài nguyên đã sinh ra vào một tập để staging:

```xml
<property name="main.resources.dir" location="src/main/resources"/>
<property name="generated.resources.dir" location="build/generated-resources"/>
<property name="stage.dir" location="build/stage"/>

<target name="stage-resources">
    <mkdir dir="${stage.dir}"/>
    <copy todir="${stage.dir}">
        <union>
            <fileset dir="${main.resources.dir}"/>
            <fileset dir="${generated.resources.dir}"/>
        </union>
    </copy>
</target>
```

Task `copy` nhận một ResourceCollection được tạo từ hai `fileset`. Mọi resource thuộc một trong hai tập đều được đưa vào quá trình copy. Nếu cùng một resource được đưa vào collection nhiều lần và Ant nhận diện chúng là trùng, `union` chỉ giữ một phần tử.

### Đặt tên union để tái sử dụng

Khi nhiều task cần cùng một tập tài nguyên, có thể khai báo `union` ở cấp project với `id` rồi tham chiếu bằng `refid`:

```xml
<union id="application.resources">
    <fileset dir="src/main/resources"/>
    <fileset dir="build/generated-resources"/>
</union>

<target name="stage-resources">
    <copy todir="build/stage">
        <union refid="application.resources"/>
    </copy>
</target>

<target name="backup-resources">
    <copy todir="build/backup">
        <union refid="application.resources"/>
    </copy>
</target>
```

`id` đặt tên cho collection dùng chung. `refid` yêu cầu task sử dụng lại collection đó ở vị trí chấp nhận ResourceCollection. Hai target có thể dùng cùng tập tài nguyên mà không phải lặp lại các khai báo `fileset`. Hãy kiểm tra task cụ thể có hỗ trợ ResourceCollection hay không trước khi lồng một collection vào task đó.

## 3. Phép giao với `intersect`

`intersect` chỉ giữ các resource xuất hiện trong tất cả các collection đầu vào. Với hai tập A và B:

\[A \cap B = \{x \mid x \in A \text{ và } x \in B\}\]

Ví dụ, project có nhiều file XML nhưng chỉ muốn xử lý các XML nằm trong thư mục `schemas`. Có thể tạo hai fileset trên cùng một gốc tài nguyên: một tập chứa tất cả XML, tập còn lại chứa XML trong `schemas`.

```xml
<target name="copy-schema-xml">
    <mkdir dir="build/schema-xml"/>
    <copy todir="build/schema-xml">
        <intersect>
            <fileset dir="src/main/resources"
                     includes="**/*.xml"/>
            <fileset dir="src/main/resources"
                     includes="schemas/**/*.xml"/>
        </intersect>
    </copy>
</target>
```

Kết quả là các resource thuộc cả hai fileset. Trong ví dụ này, tập thứ hai là một tập con của tập thứ nhất, nên kết quả tương ứng với các file XML trong `schemas`.

### Điều kiện để phép giao có ý nghĩa

`intersect` so sánh các Resource, không đơn giản so sánh tên tương đối mà con người nhìn thấy trong cây thư mục. Nếu hai fileset dùng hai thư mục gốc khác nhau, `a/config.xml` trong tập này và `b/config.xml` trong tập kia là hai file khác nhau dù phần tên tương đối giống nhau. Vì vậy, ví dụ tìm giao của các file trong cùng một cây thư mục nên dùng cùng `dir` và các điều kiện include khác nhau.

Khi kết hợp nhiều loại ResourceCollection, kết quả còn phụ thuộc cách kiểu Resource cụ thể định nghĩa equality. Nếu cần giao giữa các nguồn khác loại, hãy kiểm tra cách chúng định danh resource và xác nhận kết quả trên dữ liệu thực tế.

## 4. Phép hiệu với `difference`

`difference` giữ các resource thuộc collection đầu tiên nhưng không xuất hiện trong các collection đứng sau. Với hai tập A và B:

\[A \setminus B = \{x \mid x \in A \text{ và } x \notin B\}\]

Ví dụ, thư mục tài nguyên có file cấu hình thật và các file mẫu `.example`. Khi staging, có thể lấy toàn bộ tài nguyên rồi loại các file mẫu:

```xml
<target name="stage-production-resources">
    <mkdir dir="build/production-resources"/>
    <copy todir="build/production-resources">
        <difference>
            <fileset dir="src/main/resources"/>
            <fileset dir="src/main/resources"
                     includes="**/*.example"/>
        </difference>
    </copy>
</target>
```

Collection đầu tiên là tập tài nguyên gốc. Collection thứ hai mô tả nhóm cần loại. Kết quả chỉ gồm các resource thuộc tập gốc và không có trong tập loại trừ.

### Loại nhiều nhóm tài nguyên

Khi cần loại nhiều nhóm, có thể đặt một `union` làm collection thứ hai của `difference`. Khi đó tập bị loại là hợp của tất cả các nhóm bên trong union:

```xml
<target name="stage-release-resources">
    <copy todir="build/release-resources">
        <difference>
            <fileset dir="src/main/resources"/>
            <union>
                <fileset dir="src/main/resources"
                         includes="**/*.example"/>
                <fileset dir="src/main/resources"
                         includes="**/draft/**"/>
                <fileset dir="src/main/resources"
                         includes="**/*.local"/>
            </union>
        </difference>
    </copy>
</target>
```

Có thể hiểu kết quả là:

\[A \setminus (B \cup C \cup D)\]

Trong ví dụ, các file `.example`, file nằm dưới thư mục `draft` và file `.local` bị loại khỏi tập tài nguyên phát hành.

Với ba hoặc nhiều collection con trực tiếp, `difference` vẫn lấy collection đầu tiên làm tập gốc và loại các resource có trong các collection còn lại. Để biểu đạt rõ ý định, khi cần loại nhiều nhóm phức tạp, nên gom các nhóm đó vào một `union` như ví dụ.

## 5. Kết hợp các phép toán

Các resource collection có thể lồng nhau. Điều này cho phép mô tả quy tắc chọn tài nguyên theo từng lớp: trước tiên hợp các nguồn, sau đó giao với tập được phép phát hành, hoặc lấy hiệu để loại tài nguyên nội bộ.

Ví dụ, giả sử:

- `src/main/resources` chứa tài nguyên do nhóm phát triển quản lý.
- `build/generated-resources` chứa tài nguyên được sinh tự động.
- Chỉ các file nằm dưới `public/` trong nguồn chính được phép đưa vào ví dụ staging này.

Có thể lấy hợp của hai nguồn rồi giao với allowlist:

```xml
<union id="all.resources">
    <fileset dir="src/main/resources"/>
    <fileset dir="build/generated-resources"/>
</union>

<target name="stage-allowed-resources">
    <copy todir="build/release-resources">
        <intersect>
            <union refid="all.resources"/>
            <fileset dir="src/main/resources"
                     includes="public/**/*"/>
        </intersect>
    </copy>
</target>
```

Trong ví dụ này, `intersect` chỉ giữ các resource thuộc cả `all.resources` và fileset `public/**/*` của nguồn chính. Vì hai collection cùng tham chiếu đến file trong `src/main/resources`, Ant có thể nhận diện các resource chung. Các resource được sinh trong `build/generated-resources` không nằm trong fileset thứ hai nên bị loại khỏi kết quả. Một danh sách tên file đặt ở thư mục khác không tự động trở thành allowlist tương đương chỉ vì tên tương đối giống nhau; `intersect` cần các Resource được định danh tương ứng.

Trong thực tế, hãy ưu tiên cấu trúc đơn giản có thể giải thích được. Một biểu thức lồng quá nhiều lớp sẽ khó bảo trì nếu người đọc không thể xác định tập gốc, tập bổ sung và tập bị loại.

## 6. So sánh nhanh ba phép toán

Giả sử các tập tài nguyên:

- A = `{a.xml, b.xml, c.txt}`
- B = `{b.xml, c.txt, d.json}`

Kết quả:

| Phép toán | Kết quả | Ý nghĩa |
|---|---|---|
| `union(A, B)` | `{a.xml, b.xml, c.txt, d.json}` | Có trong A hoặc B |
| `intersect(A, B)` | `{b.xml, c.txt}` | Có trong cả A và B |
| `difference(A, B)` | `{a.xml}` | Có trong A nhưng không có trong B |

Điểm quan trọng là `difference` có hướng: đổi thứ tự A và B sẽ cho kết quả khác. `union` và `intersect` về mặt tập hợp không phụ thuộc thứ tự các tập đầu vào, dù không nên dựa vào thứ tự duyệt để quyết định thứ tự ghi file.

## 7. Sử dụng collection với các task Ant

Các phép toán trên tạo ra ResourceCollection. Chúng không tự copy, xóa, validate hoặc đóng gói file. Một task tương thích mới tiêu thụ collection và thực hiện công việc.

Ví dụ với `copy`:

```xml
<copy todir="build/stage">
    <union>
        <fileset dir="src/main/resources"/>
        <fileset dir="src/extra-resources"/>
    </union>
</copy>
```

Không phải task nào cũng nhận ResourceCollection hoặc nhận mọi kiểu ResourceCollection. Hãy kiểm tra nested element mà task hỗ trợ. Việc một data type có thể tham chiếu bằng `id`/`refid` không có nghĩa task bất kỳ đều có thể tiêu thụ nó.

## 8. Tính duy nhất, equality và va chạm đầu ra

Ba phép toán làm việc với Resource, không chỉ với chuỗi tên file. Có hai vấn đề thường gây nhầm lẫn:

**Trùng resource trong collection.** `union` loại bỏ resource trùng theo equality của đối tượng Resource. Hai đường dẫn được viết khác nhau nhưng trỏ đến cùng một file có được xem là cùng resource hay không phụ thuộc cách Resource được tạo và định danh. Khi trộn nhiều loại collection, đừng suy luận equality chỉ từ tên hiển thị.

**Hai resource khác nhau có cùng tên tương đối.** Ví dụ `src/main/resources/config/app.xml` và `src/extra-resources/config/app.xml` là hai file nguồn khác nhau. Cả hai có thể cùng xuất hiện trong union, dù khi copy về một thư mục đích chúng cùng tạo ra đường dẫn `config/app.xml`. Union không tự giải quyết xung đột tên đích cho bạn.

Để tránh kết quả phụ thuộc ngẫu nhiên:

- Tránh để nhiều nguồn có cùng đường dẫn tương đối nếu chúng được copy vào chung một thư mục.
- Nếu hai file cùng tên có ý nghĩa khác nhau, hãy đổi tên hoặc staging vào các thư mục riêng.
- Nếu một nguồn phải ưu tiên nguồn khác, hãy thể hiện quy tắc ưu tiên bằng các collection và task rõ ràng; không dựa vào thứ tự duyệt của `union`.
- Với `intersect` và `difference`, kiểm tra equality của resource bằng các collection có cùng kiểu định danh và cùng cách biểu diễn đường dẫn.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `union` có nhiều file cùng tên | Chúng là hai Resource khác nhau ở hai thư mục gốc | Kiểm tra đường dẫn đầy đủ; giải quyết xung đột tên ở đích |
| `intersect` trả về rỗng dù tên file giống nhau | Resource đến từ hai root hoặc hai kiểu nguồn khác nhau nên không bằng nhau | Dùng cùng root/định danh hoặc xác minh cách Resource so sánh equality |
| `difference` loại sai tài nguyên | Đặt nhầm collection đầu tiên hoặc tập loại trừ không mô tả đúng resource cần bỏ | Xác định A là tập gốc; đưa các tập cần loại vào sau |
| Task báo không hỗ trợ nested collection | Task không chấp nhận ResourceCollection hoặc kiểu resource đó | Kiểm tra tài liệu task và dùng collection/task tương thích |
| Copy ghi đè file ngoài dự kiến | Nhiều Resource khác nhau ánh xạ đến cùng đường dẫn đích | Tách staging hoặc quy định ánh xạ/tên file rõ ràng |
| Danh sách resource khó hiểu | Collection lồng nhau quá sâu hoặc tên nguồn không mô tả mục đích | Đặt `id` có ý nghĩa và tách collection thành các khối nhỏ |

Khi debug, hãy bắt đầu bằng một collection nhỏ và dùng task tiêu thụ quen thuộc như `copy` vào một thư mục staging riêng. So sánh các file kết quả với tập mong muốn trước khi đưa collection vào bước đóng gói hoặc phát hành.

## 10. Quy tắc tổ chức buildfile

- Dùng `union` khi cần gom nhiều nguồn tài nguyên thành một tập.
- Dùng `intersect` khi cần giữ tài nguyên có mặt trong mọi tập đầu vào.
- Dùng `difference` khi có một tập gốc và cần loại các nhóm tài nguyên khác khỏi tập đó.
- Đặt `id` cho collection được dùng lại ở nhiều target; tên nên diễn tả mục đích như `all.resources`, `release.resources` hoặc `source.files`.
- Giữ các phép toán đơn giản; nếu lồng nhiều lớp, giải thích rõ collection nào là nguồn, collection nào là allowlist hoặc blacklist.
- Chú ý equality của Resource khi dùng `intersect` và `difference`, nhất là khi trộn `fileset`, `filelist`, `path` hoặc resource trong archive.
- Kiểm tra va chạm tên đích trước khi copy hoặc đóng gói nhiều nguồn.
- Chỉ đưa resource collection vào task có hỗ trợ nested ResourceCollection.
- Không xem các phép toán này là target; chúng chỉ xác định tập đầu vào cho task.

## 11. Bài tập tự kiểm tra

**Bài 1.** Có hai fileset A và B. Muốn lấy mọi resource thuộc A hoặc B, dùng phép toán nào?

**Đáp án:** Dùng `union`.

**Bài 2.** Muốn chỉ giữ file xuất hiện trong cả hai collection, dùng phép toán nào?

**Đáp án:** Dùng `intersect`. Cần bảo đảm các Resource được so sánh theo cùng định danh; tên tương đối giống nhau chưa chắc đại diện cùng một resource.

**Bài 3.** Muốn lấy toàn bộ tài nguyên trong thư mục nhưng bỏ các file `.local`, collection nào nên đứng đầu trong `difference`?

**Đáp án:** Fileset chứa toàn bộ tài nguyên phải đứng đầu; fileset chứa `**/*.local` đứng sau làm tập loại trừ.

**Bài 4.** Nếu hai fileset có file `config/app.xml` ở hai thư mục gốc khác nhau, `union` có chắc chỉ giữ một file không?

**Đáp án:** Không. Hai file vật lý khác nhau là hai resource khác nhau dù tên tương đối giống nhau. Nếu copy chung về một đích, cần xử lý va chạm tên.

**Bài 5.** `difference` với ba collection A, B và C giữ những resource nào?

**Đáp án:** Giữ resource thuộc A nhưng không thuộc B hoặc C, tức A trừ hợp của B và C.

## Kết luận

`union`, `intersect` và `difference` là các ResourceCollection dùng để kết hợp, chọn phần chung hoặc loại trừ tài nguyên trong Apache Ant. Chúng mô tả tập đầu vào cho task, còn task như `copy` mới thực hiện thao tác lên các resource đó. Khi hiểu rõ collection nào là nguồn, cách Ant xác định equality và nguy cơ trùng đường dẫn đích, buildfile có thể chọn tài nguyên linh hoạt mà vẫn dễ đọc và dự đoán được.

