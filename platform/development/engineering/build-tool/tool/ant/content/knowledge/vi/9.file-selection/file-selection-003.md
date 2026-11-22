# Kết hợp includes, excludes, includesfile và excludesfile

## 1. PatternSet và FileSet trong Ant

Khi một task Ant cần chọn một nhóm tệp để sao chép, đóng gói, xóa hoặc xử lý, nó thường nhận một `FileSet`. FileSet xác định thư mục gốc cần quét và tập quy tắc để quyết định tệp nào được chọn.

Ví dụ:

```xml
<copy todir="build/classes">
    <fileset dir="src">
        <include name="**/*.properties"/>
        <exclude name="**/test/**"/>
    </fileset>
</copy>
```

Trong ví dụ này, Ant quét bên dưới thư mục `src`, chọn các tệp `.properties` rồi loại những tệp nằm trong thư mục có tên `test`. Các phần tử `include` và `exclude` là cách khai báo PatternSet ngay bên trong FileSet.

PatternSet là tập các mẫu đường dẫn. Ant cho phép khai báo mẫu theo bốn nguồn:

- `includes`: danh sách mẫu cần bao gồm, viết trực tiếp trong thuộc tính.
- `excludes`: danh sách mẫu cần loại trừ, viết trực tiếp trong thuộc tính.
- `includesfile`: đường dẫn đến tệp chứa danh sách mẫu cần bao gồm.
- `excludesfile`: đường dẫn đến tệp chứa danh sách mẫu cần loại trừ.

Bốn nguồn này có thể kết hợp trong cùng một FileSet hoặc PatternSet. Việc kết hợp giúp giữ quy tắc đơn giản ngay trong `build.xml` và chuyển các danh sách dài, dùng chung hoặc thay đổi theo môi trường sang các tệp cấu hình riêng.

## 2. Cú pháp pattern của Ant

Pattern được so khớp với đường dẫn tương đối từ thư mục gốc của FileSet. Trong pattern, nên dùng dấu gạch chéo xuôi `/` làm dấu phân cách thư mục, kể cả khi build chạy trên Windows.

Các ký tự đại diện quan trọng:

| Ký hiệu | Ý nghĩa |
|---|---|
| `*` | Khớp với không hoặc nhiều ký tự trong một thành phần đường dẫn, không đi qua dấu phân cách thư mục |
| `?` | Khớp với đúng một ký tự trong một thành phần đường dẫn |
| `**` | Khớp với nhiều cấp thư mục, có thể là không cấp nào |

Ví dụ, giả sử FileSet có `dir="src"` và cấu trúc thư mục như sau:

```text
src/
├── Main.java
├── config/
│   └── app.xml
├── service/
│   ├── OrderService.java
│   └── OrderServiceTest.java
└── generated/
    └── ApiClient.java
```

Một số pattern thường gặp:

| Pattern | Kết quả mong muốn |
|---|---|
| `*.java` | Tệp Java ngay trong thư mục gốc `src` |
| `**/*.java` | Tệp Java ở thư mục gốc và mọi cấp thư mục con |
| `service/*.java` | Tệp Java ngay trong thư mục `service` |
| `**/generated/**` | Mọi tệp bên trong thư mục `generated` ở bất kỳ cấp nào |
| `**/*Test.java` | Tệp Java có tên kết thúc bằng `Test.java` ở mọi cấp |
| `config/?pp.xml` | Tệp như `config/app.xml`, với một ký tự bất kỳ ở vị trí dấu `?` |

Điểm dễ nhầm là `*` và `**` không giống nhau. `*` không đi xuyên qua dấu phân cách thư mục; `**` được dùng khi cần khớp qua nhiều cấp thư mục. Vì thế, `*.java` chỉ chọn tệp ở gốc FileSet, còn `**/*.java` bao phủ cả cây thư mục.

Không nên viết tiền tố thư mục của FileSet lặp lại trong pattern. Với `dir="src"`, pattern `**/*.java` đã được tính từ `src`; viết `src/**/*.java` sẽ tìm một thư mục con tên `src` bên trong thư mục gốc đó.

## 3. Quy tắc kết hợp include và exclude

Ant tổng hợp các mẫu include từ các nguồn include, và tổng hợp các mẫu exclude từ các nguồn exclude. Các mẫu trong cùng một nhóm có quan hệ OR:

- Một tệp chỉ cần khớp với ít nhất một include pattern để vượt qua điều kiện include.
- Một tệp khớp với bất kỳ exclude pattern nào sẽ bị loại.
- Exclude có hiệu lực loại trừ dù tệp đã khớp include.
- Nếu không có include pattern nào được khai báo, phía include mặc định chấp nhận tất cả tệp trong phạm vi quét; các exclude vẫn tiếp tục được áp dụng.

Có thể biểu diễn kết quả theo logic:

```text
ĐƯỢC CHỌN =
    (không có include pattern HOẶC khớp ít nhất một include)
    VÀ
    (không khớp bất kỳ exclude pattern nào)
```

Do đó, các pattern không hoạt động theo kiểu “include sau ghi đè exclude trước” hay ngược lại. Thứ tự khai báo không làm một exclude bị vô hiệu hóa bởi một include xuất hiện sau nó. Exclude luôn loại tệp đã khớp mẫu loại trừ.

Ví dụ:

```xml
<fileset dir="src"
         includes="**/*.java"
         excludes="**/*Test.java"/>
```

Tất cả tệp Java được chọn trước, sau đó tệp có tên kết thúc bằng `Test.java` bị loại. Kết quả vẫn loại test dù tệp đó khớp `**/*.java`.

Nếu chỉ khai báo:

```xml
<fileset dir="src"
         excludes="**/generated/**"/>
```

Ant chọn tất cả tệp trong phạm vi FileSet, ngoại trừ các tệp khớp đường dẫn dưới thư mục `generated`.

## 4. Dùng includes và excludes trực tiếp trong build.xml

Hai thuộc tính `includes` và `excludes` nhận danh sách pattern phân tách bằng dấu phẩy hoặc khoảng trắng. Cách này phù hợp với một số ít quy tắc ngắn, ổn định và chỉ dùng tại một vị trí.

```xml
<copy todir="build/classes">
    <fileset dir="src">
        <include name="**/*.java"/>
        <include name="**/*.properties"/>
        <exclude name="**/generated/**"/>
        <exclude name="**/*Test.java"/>
    </fileset>
</copy>
```

Có thể viết các mẫu ngay trên thuộc tính:

```xml
<copy todir="build/classes">
    <fileset dir="src"
             includes="**/*.java,**/*.properties"
             excludes="**/generated/**,**/*Test.java"/>
</copy>
```

Hai cách khai báo trên có ý nghĩa tương đương trong trường hợp đơn giản. Phần tử lồng nhau thường dễ đọc hơn khi có nhiều quy tắc hoặc khi cần gắn thêm thuộc tính cho từng phần tử. Thuộc tính danh sách gọn hơn khi chỉ có vài pattern.

## 5. Lưu pattern trong includesfile và excludesfile

Khi danh sách pattern dài hoặc được dùng ở nhiều nơi, có thể lưu chúng trong các tệp riêng. Mỗi dòng chứa một pattern.

Ví dụ cấu trúc:

```text
project/
├── build.xml
├── config/
│   ├── source-includes.txt
│   └── source-excludes.txt
└── src/
    ├── Main.java
    ├── config/
    │   └── app.xml
    └── generated/
        └── ApiClient.java
```

Nội dung `config/source-includes.txt`:

```text
**/*.java
**/*.xml
**/*.properties
```

Nội dung `config/source-excludes.txt`:

```text
**/generated/**
**/*Test.java
**/testdata/**
```

Có thể nạp hai danh sách bằng thuộc tính `includesfile` và `excludesfile`:

```xml
<copy todir="build/classes">
    <fileset dir="src"
             includesfile="${basedir}/config/source-includes.txt"
             excludesfile="${basedir}/config/source-excludes.txt"/>
</copy>
```

Ant đọc các dòng trong tệp danh sách như các pattern. Các pattern vẫn được so khớp tương đối với thư mục `dir` của FileSet, không phải tương đối với thư mục chứa tệp danh sách.

Cần phân biệt hai loại đường dẫn:

- `includesfile` và `excludesfile` trỏ đến tệp văn bản chứa quy tắc.
- Các pattern bên trong những tệp đó mô tả đường dẫn của tệp cần chọn hoặc loại trong FileSet.

Vì vậy, trong ví dụ trên, `config/source-includes.txt` là đường dẫn đến file cấu hình, còn `**/*.java` là pattern được áp dụng bên trong cây `src`.

Mỗi dòng nên chứa đúng một pattern. Tránh thêm dấu nháy quanh pattern; dấu nháy có thể bị coi là ký tự của tên mẫu thay vì cú pháp bao chuỗi như trong shell. Để dễ dùng trên nhiều hệ điều hành, dùng `/` trong pattern và giữ encoding của tệp danh sách thống nhất với môi trường build.

## 6. Kết hợp cả bốn nguồn trong một FileSet

Các nguồn inline và file-based có thể được dùng cùng nhau. Ví dụ, quy tắc chính có thể nằm trong `build.xml`, còn danh sách mở rộng và danh sách loại trừ dùng chung được đặt trong file.

```xml
<copy todir="build/classes">
    <fileset dir="${basedir}/src"
             includes="**/*.java"
             includesfile="${basedir}/config/extra-includes.txt"
             excludes="**/generated/**"
             excludesfile="${basedir}/config/common-excludes.txt"/>
</copy>
```

`config/extra-includes.txt`:

```text
**/*.xml
**/*.properties
```

`config/common-excludes.txt`:

```text
**/*Test.java
**/testdata/**
**/fixtures/**
```

Kết quả được xác định như sau:

1. Pattern `**/*.java` từ thuộc tính `includes` chọn các tệp Java.
2. Pattern `**/*.xml` và `**/*.properties` từ `extra-includes.txt` bổ sung các loại tệp cần chọn.
3. Pattern `**/generated/**` từ thuộc tính `excludes` loại thư mục generated.
4. Các pattern trong `common-excludes.txt` loại thêm test, test data và fixtures.

Một tệp phải khớp ít nhất một trong ba include pattern và không được khớp bất kỳ exclude pattern nào mới được giữ lại. Như vậy, các pattern include từ thuộc tính và file được cộng gộp, còn các pattern exclude cũng được cộng gộp.

Không có khái niệm một include trong file có quyền “mở lại” tệp đã bị loại bởi exclude. Nếu một pattern exclude quá rộng, cần sửa hoặc thu hẹp chính quy tắc exclude đó.

## 7. Dùng phần tử lồng nhau và PatternSet tái sử dụng

Ngoài các thuộc tính trên FileSet, Ant cho phép khai báo các mẫu bằng phần tử lồng nhau. Cách này thuận tiện khi muốn nhiều nhóm pattern hoặc muốn tái sử dụng một PatternSet.

```xml
<patternset id="java-source-patterns">
    <include name="**/*.java"/>
    <includesfile name="${basedir}/config/extra-java-includes.txt"/>

    <exclude name="**/generated/**"/>
    <excludesfile name="${basedir}/config/java-excludes.txt"/>
</patternset>

<copy todir="build/classes">
    <fileset dir="${basedir}/src">
        <patternset refid="java-source-patterns"/>
    </fileset>
</copy>

<jar destfile="build/source-tools.jar">
    <fileset dir="${basedir}/src">
        <patternset refid="java-source-patterns"/>
    </fileset>
</jar>
```

Ở đây, PatternSet có id `java-source-patterns` chứa cả phần tử `include`, `includesfile`, `exclude` và `excludesfile`. Hai FileSet tham chiếu cùng một PatternSet nên sử dụng chung quy tắc chọn tệp.

Khai báo tái sử dụng giúp tránh sao chép các pattern giống nhau giữa nhiều task. Khi quy tắc chung thay đổi, chỉ cần cập nhật một PatternSet. Tuy nhiên, cần bảo đảm thư mục gốc của các FileSet có cùng ý nghĩa tương đối; cùng một pattern có thể cho kết quả khác nếu áp dụng lên hai cây thư mục khác nhau.

Với nhóm pattern chỉ dùng một lần, khai báo trực tiếp bên trong FileSet thường dễ theo dõi hơn. Với nhóm quy tắc được dùng nhiều lần, đặt id cho PatternSet giúp build file nhất quán và ngắn gọn.

## 8. Kết hợp pattern với các thiết lập FileSet khác

PatternSet quyết định tên đường dẫn nào được chấp nhận, nhưng FileSet còn có các thiết lập ảnh hưởng đến kết quả quét.

Ví dụ:

```xml
<fileset dir="src"
         casesensitive="yes"
         defaultexcludes="yes"
         followsymlinks="yes"
         includes="**/*.java"
         excludes="**/generated/**"/>
```

Một số thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| `dir` | Thư mục gốc để quét |
| `casesensitive` | Điều khiển so khớp có phân biệt chữ hoa/chữ thường; mặc định là `yes` |
| `defaultexcludes` | Bật hoặc tắt các mẫu loại trừ mặc định của Ant; mặc định là `yes` |
| `followsymlinks` | Điều khiển việc theo liên kết symbolic link khi quét; mặc định là `yes` |

Các default excludes là nhóm quy tắc loại trừ được Ant áp dụng ngoài những pattern do dự án khai báo, thường để bỏ qua metadata của hệ thống quản lý phiên bản và các tệp/thư mục không nên đóng gói. Nếu một tệp không xuất hiện dù không khớp exclude tự viết, hãy xem xét thiết lập này.

`casesensitive` ảnh hưởng đến cách so khớp pattern với tên đường dẫn. Nếu build phải chạy nhất quán trên nhiều hệ điều hành, không nên phụ thuộc vào khác biệt hoa thường giữa filesystem. Hãy viết pattern trùng chính xác với tên thư mục và tệp trong repository.

`followsymlinks` có thể ảnh hưởng đến việc các tệp được truy cập thông qua symbolic link có xuất hiện trong tập kết quả hay không. Với dự án dùng symlink, cần quyết định rõ có muốn quét theo liên kết hay không và kiểm tra trên môi trường build thực tế.

Pattern chỉ là một lớp lọc. Một task cụ thể còn có thể áp dụng selector hoặc điều kiện riêng, vì vậy một tệp khớp include chưa chắc đã được task cuối cùng xử lý nếu còn bộ lọc khác.

## 9. Những lỗi thường gặp khi kết hợp bốn nguồn

### Một tệp đã include nhưng vẫn không được chọn

Kiểm tra toàn bộ exclude pattern, bao gồm cả thuộc tính `excludes` và file `excludesfile`. Chỉ cần khớp một mẫu loại trừ là tệp bị loại. Cũng cần xem default excludes và các selector khác nếu task có dùng.

### Include trong file không bổ sung tệp như mong đợi

Nếu đã có include pattern, tệp phải khớp ít nhất một pattern trong toàn bộ nhóm include. Kiểm tra đường dẫn tương đối từ `dir`, cách viết `**`, tên phần mở rộng và chữ hoa/chữ thường. Đừng giả định pattern được tính từ vị trí file `includesfile`.

### Tệp trong thư mục gốc không được chọn

Pattern `*.java` chỉ nhắm đến tệp trong thư mục gốc của FileSet. Nếu muốn lấy cả thư mục con, dùng `**/*.java`.

### Pattern loại trừ không tác động

Đảm bảo pattern được viết tương đối với thư mục gốc, ví dụ `**/generated/**` để loại thư mục generated ở mọi cấp. Nếu chỉ viết `generated/**`, mẫu sẽ nhắm đến thư mục `generated` ở ngay cấp gốc của FileSet.

### Tệp danh sách không được tìm thấy

Kiểm tra đường dẫn thuộc tính `includesfile` hoặc `excludesfile`, quyền đọc và thư mục làm việc khi chạy Ant. Dùng `${basedir}` hoặc đường dẫn tuyệt đối đã xác định để tránh phụ thuộc vào nơi người dùng gọi lệnh.

### Thay đổi file danh sách nhưng kết quả không đổi

Đảm bảo task đang dùng đúng FileSet và đúng đường dẫn file danh sách. Nếu có nhiều file cấu hình cùng tên ở các thư mục khác nhau, log đường dẫn thực tế hoặc dùng đường dẫn rõ ràng để tránh đọc nhầm file. Chạy lại task và quan sát danh sách tệp mà task xử lý.

## 10. Kiểm tra tập tệp được chọn

Khi các quy tắc trở nên phức tạp, nên quan sát danh sách kết quả trước khi dùng FileSet để đóng gói hoặc xóa dữ liệu. Có thể dùng `pathconvert` để chuyển tập đường dẫn thành một property rồi in ra:

```xml
<target name="show-selected-files">
    <pathconvert property="selected.files" pathsep="${line.separator}">
        <fileset dir="${basedir}/src"
                 includes="**/*.java"
                 includesfile="${basedir}/config/extra-includes.txt"
                 excludes="**/generated/**"
                 excludesfile="${basedir}/config/common-excludes.txt"/>
    </pathconvert>

    <echo message="Selected files:${line.separator}${selected.files}"/>
</target>
```

Chạy:

```bash
ant show-selected-files
```

Kết quả giúp xác nhận pattern thực tế đang chọn những đường dẫn nào. Nếu danh sách trống hoặc thiếu tệp, có thể kiểm tra lần lượt include, exclude, đường dẫn gốc, default excludes và tên file cấu hình.

Với task `copy`, cũng có thể bật thuộc tính `verbose="true"` để quan sát các tệp được sao chép. Nên kiểm tra tập tệp trên một thư mục thử nghiệm trước khi áp dụng pattern mới vào task có tác động lớn như xóa hoặc đóng gói phát hành.

## 11. Nguyên tắc tổ chức quy tắc chọn tệp

- Đặt các pattern ngắn và đặc thù của một task ngay trong `build.xml`.
- Chuyển danh sách dài hoặc được nhiều task dùng chung sang `includesfile` và `excludesfile`.
- Dùng include để xác định tập tệp cần xử lý, sau đó dùng exclude để loại các ngoại lệ; nhớ rằng chỉ cần khớp một exclude là tệp bị loại.
- Giữ pattern tương đối với thư mục gốc FileSet và dùng `/` làm dấu phân cách.
- Tách file include và exclude theo mục đích rõ ràng, ví dụ danh sách loại tệp nguồn, tài nguyên runtime, test và generated.
- Tái sử dụng PatternSet có id khi nhiều task cần cùng một quy tắc và cùng ý nghĩa thư mục gốc.
- Kiểm tra danh sách tệp kết quả trước khi đưa quy tắc mới vào quy trình đóng gói hoặc xóa.
- Tránh đưa secret hoặc thông tin môi trường nhạy cảm vào file pattern; các file này chỉ nên chứa quy tắc chọn đường dẫn.

`includes` và `includesfile` hợp nhất các mẫu cần chọn; `excludes` và `excludesfile` hợp nhất các mẫu cần loại. Ant chọn tệp khớp ít nhất một include (hoặc tất cả tệp nếu không có include) rồi loại mọi tệp khớp bất kỳ exclude nào. Nắm rõ cách kết hợp này giúp quản lý danh sách tệp lớn, chia sẻ quy tắc giữa các task và tránh đóng gói nhầm tài nguyên.

