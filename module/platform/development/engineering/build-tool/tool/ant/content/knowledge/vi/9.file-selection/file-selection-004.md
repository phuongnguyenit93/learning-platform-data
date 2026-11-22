# Các mẫu loại trừ mặc định và defaultexcludes

Khi dùng Apache Ant để chọn tệp, bạn thường không muốn lấy mọi tệp có trong một thư mục. Một dự án có thể chứa mã nguồn, tài nguyên cần đóng gói, tệp tạm của trình soạn thảo, dữ liệu quản lý phiên bản và các tệp sinh ra trong quá trình làm việc. Nếu quét toàn bộ mà không lọc, build có thể vô tình đóng gói cả metadata của Git, thư mục Subversion hoặc tệp backup.

Ant hỗ trợ **default excludes** (các mẫu loại trừ mặc định) để tự động bỏ qua một số tên tệp và thư mục phổ biến. Thuộc tính `defaultexcludes` của `fileset` cho phép bật hoặc tắt nhóm loại trừ này cho một lần quét. Task cùng tên `defaultexcludes` cho phép xem và điều chỉnh danh sách mẫu mặc định dùng bởi Ant.

Bài học này giải thích cách Ant chọn tệp bằng pattern, các mẫu loại trừ mặc định thường gặp, phạm vi của `defaultexcludes`, và cách kết hợp chúng với `include`/`exclude` khi đóng gói hoặc sao chép dữ liệu.

## 1. Vì sao cần mẫu loại trừ?

Giả sử dự án có cấu trúc:

```text
project/
├── src/
│   ├── Main.java
│   ├── config.yml
│   ├── Main.java~
│   └── .gitignore
├── .git/
│   ├── HEAD
│   └── objects/
├── build/
└── README.md
```

Nếu một task sao chép toàn bộ nội dung từ thư mục gốc vào thư mục phát hành, những tệp như `Main.java~`, `.gitignore` hoặc thư mục `.git/` có thể không phải nội dung mà người dùng cuối cần.

Một `fileset` thường được dùng để mô tả tập tệp đầu vào:

```xml
<copy todir="dist">
    <fileset dir=".">
        <include name="**/*"/>
    </fileset>
</copy>
```

Mẫu `**/*` có ý nghĩa lấy các tệp ở mọi cấp bên dưới thư mục gốc. Tuy nhiên, Ant còn áp dụng các mẫu loại trừ mặc định của nó cho `fileset` theo cấu hình mặc định. Vì thế, một số tệp metadata và tệp tạm quen thuộc được bỏ qua mà không cần khai báo từng mẫu trong build file.

Các mẫu mặc định giúp giảm cấu hình lặp lại và tránh đưa những dữ liệu không mong muốn vào archive, bản phân phối hoặc báo cáo.

## 2. Pattern trong Ant

Ant dùng các pattern theo đường dẫn tương đối với thư mục gốc của `fileset`. Các ký tự đại diện thường gặp:

| Ký hiệu | Ý nghĩa |
|---|---|
| `*` | Khớp không hoặc nhiều ký tự trong một thành phần đường dẫn |
| `?` | Khớp đúng một ký tự trong một thành phần đường dẫn |
| `**` | Khớp không hoặc nhiều cấp thư mục |

Ví dụ:

| Pattern | Ví dụ khớp |
|---|---|
| `*.java` | `Main.java` ở ngay thư mục gốc của fileset |
| `**/*.java` | `Main.java`, `src/Main.java`, `src/app/Main.java` |
| `src/**` | Các tệp và thư mục bên dưới `src` |
| `**/*.tmp` | Tệp `.tmp` ở thư mục gốc hoặc các thư mục con |
| `**/backup/*` | Các mục trực tiếp bên trong thư mục tên `backup` ở mọi cấp |

`**` là điểm quan trọng khi lọc cây thư mục. Ví dụ `*.tmp` chỉ mô tả tên tệp trong một cấp đường dẫn; `**/*.tmp` mô tả tệp có phần mở rộng `.tmp` ở bất kỳ cấp nào bên dưới base directory.

Trong Ant, pattern được so khớp theo quy tắc của Ant `DirectoryScanner`, không phải quy tắc wildcard của terminal. Đừng giả định rằng dấu `*` hoặc `**` hoạt động giống hệt lệnh `dir`, PowerShell hay shell Linux.

## 3. Default excludes là gì?

**Default excludes** là một tập pattern mà Ant tự động áp dụng khi quét `fileset` theo cấu hình mặc định. Chúng chủ yếu nhằm bỏ qua metadata của hệ thống quản lý phiên bản, tệp tạm do trình soạn thảo tạo ra và một số tệp phụ trợ của hệ điều hành hoặc công cụ phát triển.

Các ví dụ thường gặp gồm:

- Thư mục metadata của CVS: `CVS/` và nội dung bên trong.
- Thư mục metadata của Subversion: `.svn/` và nội dung bên trong.
- Thư mục metadata của Git: `.git/` và nội dung bên trong.
- Thư mục metadata của Mercurial hoặc Bazaar trong các phiên bản Ant có hỗ trợ mẫu tương ứng.
- Tệp backup có đuôi `~`.
- Tệp lock hoặc tệp tạm do một số trình soạn thảo tạo ra, chẳng hạn mẫu `.#...` hoặc `#...#`.
- Một số tệp metadata của hệ điều hành hoặc công cụ như `.DS_Store`, `Thumbs.db` hay `._...`, tùy phiên bản Ant.

Đây là các nhóm ví dụ, không phải danh sách đầy đủ và cố định cho mọi phiên bản. Danh sách cụ thể có thể được mở rộng theo phiên bản Ant. Khi cần biết chính xác môi trường hiện tại đang loại trừ pattern nào, hãy dùng task `defaultexcludes` với thuộc tính `echo`.

Ví dụ:

```xml
<target name="show-default-excludes">
    <defaultexcludes echo="true"/>
</target>
```

Chạy:

```bash
ant show-default-excludes
```

Ant in danh sách default excludes hiện hành vào log. Đây là cách đáng tin cậy hơn việc sao chép một danh sách từ tài liệu của phiên bản khác rồi giả định máy đang chạy có cùng danh sách.

### Default excludes không phải là mọi tệp ẩn

Không nên hiểu default excludes là “bỏ qua tất cả tệp bắt đầu bằng dấu chấm”. Ant chỉ bỏ qua các đường dẫn khớp với pattern đã được định nghĩa.

Ví dụ, `.env`, `.editorconfig` hoặc `.gitignore` có thể vẫn được chọn nếu không có pattern mặc định hoặc pattern riêng loại trừ chúng. Tương tự, một tệp cấu hình bắt đầu bằng dấu chấm không tự động bị bỏ qua chỉ vì tên của nó là hidden file trên một hệ điều hành.

Nếu dự án không muốn đóng gói một tệp cấu hình cụ thể, hãy khai báo `exclude` rõ ràng thay vì dựa vào giả định rằng mọi tệp ẩn đều bị loại.

## 4. Thuộc tính defaultexcludes của fileset

`fileset` có thuộc tính `defaultexcludes` để quyết định có áp dụng tập pattern mặc định cho lần quét đó hay không.

Các giá trị thường dùng:

| Giá trị | Ý nghĩa |
|---|---|
| `yes` | Áp dụng default excludes; đây là hành vi mặc định của `fileset` |
| `no` | Không áp dụng các mẫu loại trừ mặc định cho fileset này |

Ví dụ bật default excludes một cách tường minh:

```xml
<copy todir="dist">
    <fileset dir="project" defaultexcludes="yes">
        <include name="**/*"/>
    </fileset>
</copy>
```

Trong ví dụ, Ant chọn nội dung theo `**/*`, đồng thời bỏ qua các đường dẫn khớp với default excludes.

Nếu đặt `defaultexcludes="no"`:

```xml
<copy todir="dist/repository-snapshot">
    <fileset dir="project" defaultexcludes="no">
        <include name="**/*"/>
    </fileset>
</copy>
```

Ant không tự áp dụng tập default excludes cho fileset này. Các thư mục metadata hoặc tệp backup khớp với include có thể được đưa vào kết quả.

Điều này hữu ích trong một số tác vụ đặc biệt, chẳng hạn tạo snapshot đầy đủ của cây thư mục để phân tích. Tuy nhiên, không nên tắt default excludes cho bước đóng gói thông thường nếu không có lý do rõ ràng, vì archive có thể chứa `.git/`, `.svn/`, tệp backup hoặc dữ liệu không liên quan.

### defaultexcludes="no" không tắt mọi quy tắc lọc

Thuộc tính này chỉ tắt nhóm **default excludes**. Các pattern `include` và `exclude` do bạn khai báo trong chính `fileset` vẫn có tác dụng.

Ví dụ:

```xml
<fileset dir="project" defaultexcludes="no">
    <include name="**/*"/>
    <exclude name="**/*.tmp"/>
    <exclude name="**/build/**"/>
</fileset>
```

Fileset vẫn loại các tệp `.tmp` và nội dung thư mục `build` theo cấu hình riêng, dù default excludes đã bị tắt.

## 5. Kết hợp include, exclude và default excludes

Ba cơ chế này giải quyết các mục đích khác nhau:

- `include` xác định những đường dẫn được phép tham gia tập tệp.
- `exclude` loại bỏ những đường dẫn cụ thể khỏi tập đã chọn.
- `defaultexcludes` bật hoặc tắt tập pattern mặc định của Ant.

Ví dụ, khi đóng gói tài nguyên:

```xml
<target name="copy-resources">
    <mkdir dir="dist/resources"/>

    <copy todir="dist/resources">
        <fileset dir="src">
            <include name="**/*.yml"/>
            <include name="**/*.properties"/>
            <exclude name="**/local-*.yml"/>
            <exclude name="**/secret.properties"/>
        </fileset>
    </copy>
</target>
```

Fileset chỉ lấy tệp YAML và properties, sau đó loại các cấu hình local và tệp chứa thông tin nhạy cảm theo tên. Default excludes vẫn được áp dụng vì không tắt chúng.

Nếu muốn chọn tất cả nhưng bỏ thêm một số mẫu:

```xml
<fileset dir="src">
    <include name="**/*"/>
    <exclude name="**/*.bak"/>
    <exclude name="**/*.tmp"/>
</fileset>
```

Bạn không cần tự khai báo lại các pattern mặc định như `.git/**` nếu default excludes đã xử lý chúng. Hãy chỉ thêm quy tắc riêng của dự án.

## 6. Task defaultexcludes

Ngoài thuộc tính trên `fileset`, Ant cung cấp task `defaultexcludes` để xem và điều chỉnh tập default excludes dùng bởi các thao tác quét tệp.

Task có thể được dùng để:

- In danh sách hiện hành.
- Thêm một pattern vào danh sách mặc định.
- Xóa một pattern khỏi danh sách mặc định.

### Xem danh sách hiện hành

```xml
<target name="show-default-excludes">
    <defaultexcludes echo="true"/>
</target>
```

### Thêm pattern mặc định

Giả sử nhóm muốn bỏ qua mọi tệp backup kết thúc bằng `.bak` trong các lần quét mặc định:

```xml
<target name="configure-default-excludes">
    <defaultexcludes add="**/*.bak"/>
    <defaultexcludes echo="true"/>
</target>
```

Sau khi task thêm pattern, các `fileset` sử dụng default excludes sẽ áp dụng cả pattern mới. Pattern `**/*.bak` bao phủ tệp `.bak` ở thư mục gốc và các thư mục con.

### Gỡ một pattern đã thêm

Nếu không muốn dùng quy tắc đó nữa, có thể loại bỏ chính pattern đã thêm:

```xml
<target name="remove-custom-default-exclude">
    <defaultexcludes remove="**/*.bak"/>
</target>
```

`remove` cần khớp với pattern đang có trong danh sách. Nếu mẫu không tồn tại hoặc viết khác với mẫu đã thêm, thao tác không loại bỏ được quy tắc mà bạn dự định.

### Phạm vi ảnh hưởng

Task `defaultexcludes` điều chỉnh danh sách default excludes của Ant `DirectoryScanner`, vì vậy tác động có thể ảnh hưởng đến nhiều thao tác quét tệp trong cùng tiến trình Ant, chứ không chỉ một `fileset` đơn lẻ. Các `fileset` đặt `defaultexcludes="no"` vẫn không áp dụng danh sách này.

Do phạm vi rộng, hãy cân nhắc thứ tự thực hiện và đặt cấu hình ở một vị trí dễ nhận biết trước các target cần quét tệp. Tránh thay đổi danh sách mặc định giữa các target mà không ghi rõ lý do, vì kết quả chọn tệp có thể phụ thuộc vào target nào đã chạy trước.

Nếu một quy tắc chỉ cần áp dụng cho một thư mục hoặc một tác vụ, `exclude` trong chính `fileset` thường dễ hiểu và ít ảnh hưởng hơn việc thay đổi default excludes toàn cục của tiến trình.

## 7. Ví dụ: đóng gói source nhưng bỏ metadata và tệp tạm

Giả sử dự án:

```text
sample/
├── src/
│   ├── Main.java
│   ├── Main.java~
│   ├── config/
│   │   └── app.yml
│   └── .git/
├── .git/
└── build.xml
```

Muốn tạo archive chứa mã nguồn và cấu hình cần thiết, có thể dùng:

```xml
<project name="source-package" default="package-source">

    <target name="package-source">
        <mkdir dir="dist"/>

        <zip destfile="dist/source.zip">
            <fileset dir=".">
                <include name="src/**"/>
                <include name="build.xml"/>
                <exclude name="src/**/*.tmp"/>
            </fileset>
        </zip>
    </target>

</project>
```

Trong ví dụ này:

1. `include` giới hạn nội dung trong `src/` và `build.xml`.
2. Default excludes tiếp tục loại các metadata và tệp tạm khớp với danh sách mặc định.
3. `exclude` bổ sung quy tắc riêng để bỏ tệp `.tmp` trong source.
4. Task `zip` chỉ đóng gói các tệp thuộc tập đã chọn.

Nếu thay `fileset` thành `defaultexcludes="no"`, các thư mục metadata có thể lọt vào archive nếu chúng nằm trong phạm vi include. Vì vậy, chỉ tắt default excludes khi thực sự muốn thu thập các đường dẫn đó và đã xác định rõ các mẫu thay thế cần áp dụng.

## 8. Ví dụ: một fileset cần giữ metadata, fileset khác vẫn dùng mặc định

Đôi khi cùng một build cần hai chính sách khác nhau. Ví dụ, một target đóng gói sản phẩm cần loại metadata, còn một target phân tích repository cần thu thập đầy đủ cây thư mục.

```xml
<project name="different-scan-policies" default="package">

    <target name="package">
        <zip destfile="dist/application.zip">
            <fileset dir="project" defaultexcludes="yes">
                <include name="src/**"/>
                <include name="README.md"/>
            </fileset>
        </zip>
    </target>

    <target name="snapshot">
        <zip destfile="dist/full-snapshot.zip">
            <fileset dir="project" defaultexcludes="no">
                <include name="**/*"/>
            </fileset>
        </zip>
    </target>

</project>
```

Hai target dùng chính sách khác nhau:

- `package` sử dụng default excludes để giữ archive phát hành gọn.
- `snapshot` tắt default excludes để quét toàn bộ nội dung được include.

Target `snapshot` có thể tạo archive lớn và chứa cả dữ liệu nội bộ. Trước khi dùng nó trong CI hoặc chia sẻ artifact, hãy xác định rõ có nên giữ metadata của repository và các tệp ẩn hay không.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Default excludes loại mọi tệp ẩn | Chỉ pattern có trong danh sách mới được tự động loại |
| `defaultexcludes="no"` tắt mọi exclude | Nó chỉ tắt default excludes; `include` và `exclude` riêng vẫn hoạt động |
| Tắt default excludes chỉ ảnh hưởng đến một pattern | Nó cho phép mọi đường dẫn khớp với default pattern tham gia quét, trừ khi có quy tắc khác loại chúng |
| Danh sách default excludes giống nhau ở mọi phiên bản Ant | Danh sách có thể thay đổi; dùng `echo` để xem phiên bản hiện tại |
| `defaultexcludes` task chỉ ảnh hưởng đến fileset ngay cạnh nó | Task điều chỉnh danh sách dùng bởi DirectoryScanner, nên phạm vi rộng hơn một fileset |
| Tệp `.gitignore` luôn bị loại cùng `.git/` | Metadata thư mục và tệp cấu hình có pattern riêng; không suy luận một mẫu bao phủ mọi tệp liên quan |
| `exclude` và default excludes là một cơ chế | `exclude` do build file khai báo; default excludes là bộ mẫu mặc định của Ant |

### Vì sao build file nên hạn chế thay đổi default excludes?

Default excludes là chính sách chung giúp các task quét tệp có hành vi nhất quán. Nếu mỗi target liên tục thêm hoặc gỡ pattern, người đọc khó xác định một `fileset` đang chọn những gì. Một thay đổi ở target trước có thể ảnh hưởng đến target sau.

Khi chỉ cần loại một nhóm tệp riêng trong một bước, hãy khai báo `exclude` ngay trong fileset. Chỉ thay đổi default excludes khi nhóm muốn quy tắc đó trở thành chính sách chung cho nhiều lần quét trong build.

## 10. Chẩn đoán khi tệp bị thiếu hoặc bị đưa vào ngoài ý muốn

Nếu một tệp không xuất hiện trong archive hoặc output, hãy kiểm tra:

1. Tệp có nằm bên dưới `dir` của fileset không?
2. Pattern `include` có khớp đường dẫn tương đối của tệp không?
3. Tệp có bị một pattern `exclude` riêng loại bỏ không?
4. Tệp hoặc thư mục cha có khớp default excludes không?
5. Fileset có đang đặt `defaultexcludes="no"` không?
6. Task `defaultexcludes` có thay đổi danh sách mặc định trước đó trong build không?

Nếu tệp metadata hoặc tệp tạm lại xuất hiện trong archive, hãy kiểm tra xem fileset có tắt default excludes hay không và có pattern include rộng như `**/*` hay không.

Một số cách quan sát:

```xml
<target name="inspect-default-excludes">
    <defaultexcludes echo="true"/>
</target>
```

Có thể tạo một target tạm để liệt kê các tệp mà một fileset chọn bằng task `pathconvert` hoặc task phù hợp với mục đích build, nhưng khi kiểm tra thường xuyên nên ưu tiên log của task quét và thu hẹp pattern để biết chính xác nguồn của từng tệp.

Khi cần xác minh một pattern cụ thể, hãy thử với cây thư mục nhỏ gồm một tệp khớp, một tệp không khớp và một tệp nằm ở thư mục con. Cách này giúp phân biệt lỗi pattern với lỗi do default excludes.

## 11. Ghi nhớ

- Default excludes là các pattern Ant tự áp dụng để bỏ qua metadata quản lý phiên bản, tệp tạm và một số tệp phụ trợ quen thuộc.
- Danh sách cụ thể phụ thuộc phiên bản Ant; dùng `<defaultexcludes echo="true"/>` để xem danh sách đang có.
- `fileset` mặc định áp dụng default excludes; `defaultexcludes="no"` tắt nhóm này cho fileset tương ứng.
- Tắt default excludes không tắt các quy tắc `include` và `exclude` riêng.
- Task `defaultexcludes` có thể thêm, gỡ hoặc in pattern mặc định; thay đổi danh sách có phạm vi ảnh hưởng rộng đến các lần quét trong tiến trình Ant.
- Ưu tiên `exclude` cục bộ khi quy tắc chỉ dành cho một fileset; chỉ thay đổi default excludes khi muốn một chính sách chung.
- Luôn kiểm tra nội dung archive khi thay đổi pattern quét tệp, đặc biệt với các bước đóng gói hoặc chia sẻ artifact.

Khi thiết kế `fileset`, hãy xác định rõ nội dung cần lấy, các pattern riêng cần loại bỏ và việc có áp dụng default excludes hay không. Hiểu đúng `defaultexcludes` giúp build tránh đóng gói metadata và tệp tạm, đồng thời vẫn cho phép các tác vụ đặc biệt quét toàn bộ cây thư mục khi có chủ đích.
