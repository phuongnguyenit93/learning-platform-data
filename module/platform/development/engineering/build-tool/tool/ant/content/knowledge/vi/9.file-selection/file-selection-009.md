# Kết hợp selector bằng and, or và not

Trong Apache Ant, `FileSet` giúp chọn file theo đường dẫn và các điều kiện lọc. Khi một điều kiện đơn lẻ không đủ diễn đạt yêu cầu, ta có thể kết hợp nhiều selector bằng ba phép logic: **and**, **or** và **not**. Chúng cho phép mô tả những quy tắc như “file Java đồng thời có chứa từ khóa”, “file có phần mở rộng Java hoặc Groovy”, hay “chọn file cấu hình nhưng loại thư mục sinh tự động”.

Các phần tử `<and>`, `<or>` và `<not>` là selector container. Chúng không thực hiện biên dịch hay sao chép file; chúng kết hợp kết quả đúng/sai của các selector con để quyết định một file có được chọn hay không. Hiểu đúng cách lồng các container giúp buildfile thể hiện điều kiện lọc rõ ràng, có thể đọc và thay đổi mà không phải viết nhiều target riêng.

## 1. Selector trong FileSet hoạt động như thế nào?

`FileSet` biểu diễn một tập file được chọn từ một thư mục cơ sở. Ta có thể giới hạn file bằng các pattern `include`, `exclude`, sau đó dùng selector để kiểm tra thêm thuộc tính hoặc nội dung của từng file.

Ví dụ đơn giản:

```xml
<fileset dir="src">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
</fileset>
```

Ví dụ này chọn các file có đường dẫn khớp `**/*.java` dưới `src`, đồng thời loại các file nằm trong nhánh `generated`. Pattern quyết định file nào đủ điều kiện theo đường dẫn; selector bổ sung những điều kiện khác như tên file, nội dung hoặc kích thước.

Một selector thường trả về kết quả logic cho từng file:

- `true`: file thỏa điều kiện của selector.
- `false`: file không thỏa điều kiện.

Khi có nhiều điều kiện, Ant cần kết hợp các kết quả này. Đó là nhiệm vụ của `<and>`, `<or>` và `<not>`.

## 2. Selector `<and>` — tất cả điều kiện đều phải đúng

`<and>` trả về đúng khi **tất cả selector con** đều trả về đúng. Chỉ cần một selector con không khớp, toàn bộ nhóm `<and>` không khớp.

Có thể đọc `<and>` như từ “và” trong một yêu cầu:

> Chọn file nếu nó là file Java **và** có chứa chuỗi `TODO`.

Ví dụ:

```xml
<fileset dir="src">
    <and>
        <filename name="**/*.java"/>
        <contains text="TODO"/>
    </and>
</fileset>
```

Trong ví dụ:

1. `<filename name="**/*.java"/>` kiểm tra đường dẫn file có khớp mẫu file Java hay không.
2. `<contains text="TODO"/>` kiểm tra nội dung file có chứa chuỗi `TODO` hay không.
3. `<and>` chỉ chọn file khi cả hai điều kiện cùng đúng.

Bảng kết quả của AND:

| Điều kiện A | Điều kiện B | A AND B |
|---|---|---|
| Đúng | Đúng | Đúng |
| Đúng | Sai | Sai |
| Sai | Đúng | Sai |
| Sai | Sai | Sai |

### 2.1. Dùng AND để lọc nhiều thuộc tính

Một nhóm AND có thể chứa nhiều selector hơn hai:

```xml
<fileset dir="src">
    <and>
        <filename name="**/*Service.java"/>
        <contains text="@Service"/>
        <contains text="TODO"/>
    </and>
</fileset>
```

File được chọn phải có tên khớp `*Service.java`, nội dung chứa `@Service` và đồng thời chứa `TODO`. Nếu thiếu bất kỳ điều kiện nào, file bị loại khỏi kết quả.

Điều này hữu ích khi muốn lập danh sách file cần xem xét, ví dụ tìm các service Java vẫn còn ghi chú TODO.

### 2.2. Nhiều selector trực tiếp trong FileSet

Khi đặt nhiều selector trực tiếp trong cùng một FileSet mà không bọc bằng container, Ant kết hợp chúng theo AND ngầm định: file phải thỏa tất cả selector đó.

```xml
<fileset dir="src">
    <filename name="**/*.java"/>
    <contains text="TODO"/>
</fileset>
```

Về logic, cách viết này tương đương với:

```xml
<fileset dir="src">
    <and>
        <filename name="**/*.java"/>
        <contains text="TODO"/>
    </and>
</fileset>
```

Khi điều kiện bắt đầu phức tạp, viết `<and>` tường minh thường giúp người đọc nhận ra cấu trúc logic và phân biệt nhóm điều kiện với những nhóm OR hoặc NOT được lồng bên trong.

## 3. Selector `<or>` — chỉ cần một điều kiện đúng

`<or>` trả về đúng khi **ít nhất một selector con** trả về đúng. Nếu tất cả selector con đều sai, nhóm OR không khớp.

Có thể đọc `<or>` như từ “hoặc”:

> Chọn file nếu nó là file Java **hoặc** file Groovy.

Ví dụ:

```xml
<fileset dir="src">
    <or>
        <filename name="**/*.java"/>
        <filename name="**/*.groovy"/>
    </or>
</fileset>
```

File có phần mở rộng `.java` hoặc `.groovy` đều có thể được chọn. Không yêu cầu một file phải đồng thời có hai phần mở rộng.

Bảng kết quả của OR:

| Điều kiện A | Điều kiện B | A OR B |
|---|---|---|
| Đúng | Đúng | Đúng |
| Đúng | Sai | Đúng |
| Sai | Đúng | Đúng |
| Sai | Sai | Sai |

### 3.1. OR giữa nhiều tiêu chí nội dung

OR cũng có thể kết hợp các điều kiện về nội dung:

```xml
<fileset dir="src">
    <and>
        <filename name="**/*.java"/>
        <or>
            <contains text="@Deprecated"/>
            <contains text="TODO"/>
            <contains text="FIXME"/>
        </or>
    </and>
</fileset>
```

Điều kiện tổng thể là: file phải là Java **và** nội dung phải chứa ít nhất một trong ba chuỗi `@Deprecated`, `TODO` hoặc `FIXME`.

Nếu file chứa cả ba chuỗi, nhóm OR vẫn chỉ cho kết quả đúng một lần đối với file đó. OR không tạo ra ba bản sao của cùng một file trong FileSet.

### 3.2. Khi nào nên dùng OR?

OR phù hợp khi nhiều lựa chọn khác nhau đều đáp ứng cùng một mục đích:

- Chọn nhiều phần mở rộng file, ví dụ `.java` hoặc `.groovy`.
- Chọn file chứa một trong nhiều từ khóa cần rà soát.
- Chấp nhận nhiều tên file hoặc nhiều kiểu đầu vào.
- Kết hợp các điều kiện thay thế trong một nhóm logic duy nhất.

Nếu viết nhiều selector trực tiếp trong FileSet mà muốn chúng hoạt động theo OR, hãy bọc chúng trong `<or>`. Các selector trực tiếp vốn được kết hợp theo AND ngầm định.

## 4. Selector `<not>` — phủ định một điều kiện

`<not>` đảo ngược kết quả của selector con:

- Selector con đúng thì `<not>` trả về sai.
- Selector con sai thì `<not>` trả về đúng.

Có thể đọc `<not>` như “không thỏa điều kiện” hoặc “không phải”.

Ví dụ: chọn file trong `src` nhưng loại file test có tên kết thúc bằng `Test.java`:

```xml
<fileset dir="src">
    <and>
        <filename name="**/*.java"/>
        <not>
            <filename name="**/*Test.java"/>
        </not>
    </and>
</fileset>
```

File phải là Java và không được khớp mẫu `**/*Test.java`. File `UserService.java` có thể được chọn; file `UserServiceTest.java` bị loại.

Bảng kết quả của NOT:

| Điều kiện A | NOT A |
|---|---|
| Đúng | Sai |
| Sai | Đúng |

### 4.1. NOT chỉ chứa một selector con

`<not>` được dùng để phủ định **một selector con**. Nếu muốn phủ định một nhóm nhiều điều kiện, hãy đặt nhóm đó trong một container như `<and>` hoặc `<or>`, rồi bọc container bằng `<not>`.

Ví dụ, loại file có tên kết thúc bằng `Test.java` **hoặc** `IT.java`:

```xml
<fileset dir="src">
    <not>
        <or>
            <filename name="**/*Test.java"/>
            <filename name="**/*IT.java"/>
        </or>
    </not>
</fileset>
```

Nhóm `<or>` đúng nếu file khớp một trong hai mẫu. `<not>` đảo kết quả của cả nhóm, vì vậy chỉ file không khớp cả hai mẫu mới được chọn.

Không viết nhiều selector ngang hàng trực tiếp bên trong `<not>` với ý định phủ định tất cả chúng. Hãy nhóm các điều kiện trước để biểu thức có ý nghĩa rõ ràng.

## 5. Lồng các selector container để tạo biểu thức phức hợp

Điểm mạnh của các selector container là có thể lồng chúng. Một container có thể chứa selector đơn hoặc một container khác, nhờ vậy ta mô tả được những biểu thức tương tự dấu ngoặc trong toán logic.

Ví dụ:

```xml
<fileset dir="src">
    <and>
        <filename name="**/*.java"/>
        <or>
            <contains text="TODO"/>
            <contains text="FIXME"/>
        </or>
        <not>
            <filename name="**/generated/**"/>
        </not>
    </and>
</fileset>
```

Có thể đọc biểu thức trên như sau:

```text
Là file Java
AND
(Nội dung chứa TODO OR nội dung chứa FIXME)
AND
NOT (đường dẫn nằm trong nhánh generated)
```

Một file chỉ được chọn nếu đồng thời thỏa cả ba phần:

1. Đường dẫn khớp `**/*.java`.
2. Nội dung có `TODO` hoặc `FIXME`.
3. Đường dẫn không khớp `**/generated/**`.

Đây là cách viết rõ ràng hơn việc tạo nhiều FileSet gần giống nhau rồi xử lý kết quả ở các target khác nhau.

### 5.1. Ví dụ phân tích từng file

Giả sử thư mục có các file:

```text
src/
├── main/
│   ├── UserService.java
│   └── OrderService.java
├── test/
│   └── UserServiceTest.java
└── generated/
    └── AutoService.java
```

Với điều kiện:

```xml
<and>
    <filename name="**/*.java"/>
    <contains text="TODO"/>
    <not>
        <filename name="**/generated/**"/>
    </not>
</and>
```

Ta có thể phân tích kết quả như sau (giả sử chỉ `UserService.java` và `AutoService.java` có chứa `TODO`):

| File | Là Java? | Có TODO? | Nằm trong generated? | Được chọn? |
|---|---:|---:|---:|---:|
| `main/UserService.java` | Có | Có | Không | Có |
| `main/OrderService.java` | Có | Không | Không | Không |
| `test/UserServiceTest.java` | Có | Không | Không | Không |
| `generated/AutoService.java` | Có | Có | Có | Không |

Kết quả cho thấy selector không chỉ kiểm tra từng điều kiện độc lập. Container AND yêu cầu mọi nhánh cùng đúng, còn NOT loại nhánh `generated` dù file đó có phần mở rộng Java và chứa TODO.

## 6. Kết hợp selector với include và exclude

Trong FileSet, pattern `include` và `exclude` là một lớp lọc theo đường dẫn; selector là lớp điều kiện bổ sung. Có thể kết hợp cả hai để tạo quy tắc chọn file dễ quản lý.

Ví dụ:

```xml
<fileset dir="src">
    <!-- Chỉ xét các file Java. -->
    <include name="**/*.java"/>

    <!-- Loại các file được sinh tự động. -->
    <exclude name="**/generated/**"/>

    <!-- Trong số file còn lại, chỉ lấy service có TODO. -->
    <and>
        <filename name="**/*Service.java"/>
        <contains text="TODO"/>
    </and>
</fileset>
```

Có thể hiểu quy trình lựa chọn theo các bước:

1. Ant xét file bên dưới thư mục cơ sở `src`.
2. Pattern include giới hạn ứng viên vào file Java.
3. Pattern exclude loại các đường dẫn trong `generated`.
4. Nhóm AND yêu cầu file còn lại phải có tên kết thúc bằng `Service.java` và nội dung chứa `TODO`.

Một file phải vượt qua tất cả lớp lọc mới xuất hiện trong kết quả FileSet.

Nếu không khai báo include, FileSet mặc định xem mọi file dưới thư mục cơ sở là ứng viên, trừ những file bị exclude. Selector vẫn tiếp tục lọc các ứng viên đó.

### 6.1. Nhiều selector trực tiếp và selector container

Ví dụ sau có hai selector trực tiếp:

```xml
<fileset dir="src">
    <filename name="**/*.java"/>
    <contains text="TODO"/>
</fileset>
```

Chúng được kết hợp theo AND ngầm định. Nếu muốn điều kiện tên file là Java **hoặc** Groovy, cần viết:

```xml
<fileset dir="src">
    <or>
        <filename name="**/*.java"/>
        <filename name="**/*.groovy"/>
    </or>
</fileset>
```

Không nên dựa vào việc đặt hai selector ngang hàng để biểu diễn OR. Hãy dùng `<or>` nhằm nói rõ rằng chỉ một điều kiện cần đúng.

## 7. Các selector thường được kết hợp

`and`, `or` và `not` là container, không phải điều kiện kiểm tra file cụ thể. Bên trong chúng, ta đặt các selector thực hiện việc kiểm tra.

Một số selector thường gặp:

| Selector | Mục đích |
|---|---|
| `<filename>` | Kiểm tra đường dẫn hoặc tên file theo pattern |
| `<contains>` | Kiểm tra file có chứa một chuỗi văn bản |
| `<size>` | Kiểm tra kích thước file theo ngưỡng và quan hệ so sánh |
| `<date>` | Kiểm tra thời điểm sửa đổi của file theo điều kiện ngày giờ |
| `<type>` | Phân biệt loại tài nguyên như file hoặc thư mục trong ngữ cảnh hỗ trợ |
| `<modified>` | So sánh trạng thái sửa đổi với tài nguyên tương ứng theo cấu hình mapper |

Ví dụ kết hợp tên file và nội dung:

```xml
<fileset dir="logs">
    <and>
        <filename name="**/*.log"/>
        <contains text="ERROR"/>
    </and>
</fileset>
```

Ví dụ này chọn file log có chứa chuỗi `ERROR`. Các selector khác như `size` hoặc `date` có thể được dùng khi cần lọc theo kích thước hoặc thời điểm sửa đổi; container chỉ kết hợp kết quả logic và không thay đổi ý nghĩa của selector con.

Một ví dụ khác dùng OR để chọn file có một trong hai từ khóa:

```xml
<fileset dir="config">
    <or>
        <contains text="deprecated"/>
        <contains text="legacy"/>
    </or>
</fileset>
```

File được chọn nếu nội dung có `deprecated` hoặc `legacy`. Nếu muốn chỉ lấy file `.properties` có một trong hai từ khóa, hãy thêm điều kiện tên file trong một nhóm AND:

```xml
<fileset dir="config">
    <and>
        <filename name="**/*.properties"/>
        <or>
            <contains text="deprecated"/>
            <contains text="legacy"/>
        </or>
    </and>
</fileset>
```

## 8. Tư duy biểu thức logic trước khi viết XML

Trước khi tạo selector phức tạp, nên viết yêu cầu thành câu hoặc biểu thức logic ngắn. Sau đó chuyển từng nhóm thành container XML.

Ví dụ yêu cầu:

> Chọn file cấu hình XML hoặc properties, nhưng phải nằm trong thư mục `config`, có chứa từ khóa `endpoint`, và không phải file mẫu.

Biểu thức logic:

```text
(XML OR properties)
AND contains(endpoint)
AND NOT(template)
```

Một cách biểu diễn bằng Ant:

```xml
<fileset dir=".">
    <and>
        <or>
            <filename name="config/**/*.xml"/>
            <filename name="config/**/*.properties"/>
        </or>
        <contains text="endpoint"/>
        <not>
            <filename name="config/**/*template*"/>
        </not>
    </and>
</fileset>
```

Nhóm OR chọn một trong hai loại file. Nhóm AND yêu cầu thêm nội dung `endpoint`. Nhóm NOT loại các file có `template` trong đường dẫn theo pattern đã khai báo.

Khi biểu thức có nhiều tầng, có thể thụt lề XML theo từng container để nhìn thấy cấu trúc ngoặc. Không nên viết tất cả selector trên một dòng dài vì rất khó nhận ra điều kiện nào đang được phủ định hoặc thuộc nhánh OR nào.

## 9. Các lỗi thường gặp khi kết hợp selector

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| Kết quả không có file nào | AND chứa một điều kiện quá chặt hoặc một pattern không khớp | Kiểm tra từng selector riêng rồi ghép lại từng bước |
| File thỏa một nhánh OR nhưng vẫn bị loại | Có điều kiện AND khác bên ngoài OR không thỏa | Viết biểu thức logic ra trước và kiểm tra từng nhóm |
| File bị loại dù selector con đúng | `<not>` đang đảo ngược kết quả | Xác định rõ điều kiện cần phủ định và vị trí đặt NOT |
| Dùng nhiều selector trực tiếp nhưng mong muốn OR | Selector ngang hàng trong FileSet được kết hợp theo AND ngầm định | Bọc các lựa chọn thay thế trong `<or>` |
| Đặt nhiều selector trực tiếp trong `<not>` | NOT chỉ nhận một selector con | Bọc nhiều điều kiện trong `<and>` hoặc `<or>`, rồi phủ định container đó |
| File bị loại trước khi selector được xét | `include` không khớp hoặc `exclude` đã loại file | Kiểm tra pattern include/exclude cùng selector |
| Pattern filename không khớp | Đường dẫn tương đối hoặc wildcard viết sai | Kiểm tra thư mục cơ sở và pattern của `<filename>` |
| Điều kiện contains không khớp | Nội dung không có chuỗi cần tìm hoặc cách so sánh chữ hoa/thường không như dự kiến | Kiểm tra nội dung và thuộc tính của selector `contains` |
| XML không hợp lệ | Container lồng sai cấu trúc hoặc thiếu thẻ đóng | Kiểm tra mỗi `<and>`, `<or>`, `<not>` có cấu trúc XML hợp lệ |

### 9.1. Cách cô lập điều kiện gây lọc sai

Khi FileSet trả về ít file hơn mong đợi, hãy tạm kiểm tra từng nhóm điều kiện:

1. Chỉ giữ pattern include để xác nhận tập ứng viên theo đường dẫn.
2. Thêm selector đơn đầu tiên và quan sát thay đổi.
3. Thêm các selector còn lại từng bước.
4. Với OR, kiểm tra từng nhánh thay thế.
5. Với NOT, kiểm tra selector con trước khi đảo kết quả.
6. Khi đã tìm được điều kiện gây loại file, điều chỉnh pattern hoặc cấu trúc container.

Có thể dùng một target `copy` vào thư mục thử nghiệm hoặc một task liệt kê tài nguyên phù hợp để quan sát tập file được chọn. Khi kiểm tra, hãy dùng thư mục đầu ra riêng để tránh ghi đè dữ liệu của dự án.

## 10. Ví dụ tổng hợp: chọn file nguồn cần rà soát

Giả sử dự án có mã nguồn Java và Groovy. Nhóm muốn tạo một danh sách các file cần rà soát với yêu cầu:

- Chỉ chọn file `.java` hoặc `.groovy`.
- Nội dung có `TODO` hoặc `FIXME`.
- Không chọn file nằm trong `generated`.
- Không chọn file test có hậu tố `Test` trước phần mở rộng.

Có thể viết:

```xml
<project name="selector-demo" default="collect-review-files" basedir=".">

    <property name="source.dir" location="src"/>
    <property name="review.dir" location="build/review"/>

    <target name="collect-review-files">
        <mkdir dir="${review.dir}"/>

        <copy todir="${review.dir}">
            <fileset dir="${source.dir}">
                <and>
                    <or>
                        <filename name="**/*.java"/>
                        <filename name="**/*.groovy"/>
                    </or>

                    <or>
                        <contains text="TODO"/>
                        <contains text="FIXME"/>
                    </or>

                    <not>
                        <filename name="**/generated/**"/>
                    </not>

                    <not>
                        <filename name="**/*Test.java"/>
                    </not>
                    <not>
                        <filename name="**/*Test.groovy"/>
                    </not>
                </and>
            </fileset>
        </copy>
    </target>

</project>
```

Target `collect-review-files` tạo thư mục đầu ra rồi dùng `copy` để sao chép những file thỏa toàn bộ nhóm AND. Trong nhóm đó, hai nhóm OR thể hiện các lựa chọn thay thế; các nhóm NOT loại file được sinh tự động và file test.

Đây là ví dụ minh họa cách tổ chức điều kiện. Khi áp dụng vào dự án thật, cần điều chỉnh thư mục nguồn, hậu tố test và cách xử lý cấu trúc thư mục đầu ra theo yêu cầu cụ thể. Task `copy` có thể giữ cấu trúc đường dẫn tương đối bên dưới FileSet tùy cấu hình; nếu cần một bố cục đầu ra khác, hãy xem các thuộc tính và tùy chọn của task.

## 11. Kết luận

Trong Ant, `<and>`, `<or>` và `<not>` là các selector container dùng để kết hợp kết quả của những selector con. `<and>` yêu cầu tất cả điều kiện đúng; `<or>` chỉ cần ít nhất một điều kiện đúng; `<not>` đảo ngược kết quả của một selector con. Các container có thể lồng nhau để tạo biểu thức phức hợp tương tự cách dùng ngoặc trong logic.

Khi xây dựng FileSet, hãy phân biệt pattern include/exclude với selector, nhớ rằng các selector ngang hàng được kết hợp theo AND ngầm định, và dùng container tường minh khi cần OR hoặc NOT. Viết yêu cầu lọc thành biểu thức logic trước rồi chuyển thành XML sẽ giúp điều kiện dễ đọc, dễ kiểm soát và ít gây nhầm lẫn khi dự án có nhiều quy tắc chọn file.
