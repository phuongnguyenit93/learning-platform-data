# Giới hạn tài nguyên bằng restrict và resource selector

Trong Apache Ant, nhiều task làm việc với một tập tài nguyên (*resources*): tệp trong thư mục, mục bên trong tệp ZIP, phần tử trên classpath hoặc các tài nguyên được ghép từ nhiều nguồn. Một `ResourceCollection` mô tả tập tài nguyên mà task có thể xử lý. Khi chỉ muốn đưa một phần của tập đó vào bước build, có thể dùng `restrict` kết hợp với các `ResourceSelector`.

`restrict` là một kiểu `ResourceCollection` có chức năng lọc một tập tài nguyên đầu vào. Các selector lồng bên trong quyết định tài nguyên nào được giữ lại. Cách tổ chức này tách nguồn tài nguyên khỏi điều kiện chọn, nhờ đó một quy tắc lọc có thể áp dụng cho nhiều loại nguồn và nhiều task khác nhau.

## 1. ResourceCollection và ResourceSelector

Hai khái niệm cần phân biệt:

| Thành phần | Vai trò |
|---|---|
| `ResourceCollection` | Cung cấp một tập tài nguyên để task xử lý |
| `ResourceSelector` | Kiểm tra từng tài nguyên và trả lời tài nguyên đó có được chọn hay không |
| `restrict` | Kết hợp một `ResourceCollection` đầu vào với các selector để tạo ra một tập con |

Một `FileSet` là một `ResourceCollection`: nó cung cấp các tệp được chọn dưới một thư mục gốc. `Path` cũng có thể cung cấp tài nguyên, thường là các phần tử classpath. Các kiểu như `zipfileset`, `union`, `difference` hoặc `intersect` cũng có thể tham gia xây dựng tập tài nguyên.

`ResourceSelector` không tự tìm tệp. Nó nhận một tài nguyên từ collection và quyết định có giữ tài nguyên đó hay không. Ví dụ, selector tên có thể chỉ giữ các tài nguyên có tên khớp mẫu `**/*.xml`; selector kiểu có thể chỉ giữ tài nguyên là tệp; selector kích thước có thể chỉ giữ tài nguyên vượt một ngưỡng nhất định.

`restrict` kết nối hai phía: collection cung cấp các ứng viên, selector lọc các ứng viên đó. Nó là một kiểu dữ liệu tài nguyên, không phải một task thực thi độc lập. Vì vậy, thường đặt `restrict` bên trong task nhận ResourceCollection như `copy`, `zip` hoặc trong một cấu hình ResourceCollection khác.

## 2. Cú pháp cơ bản của restrict

Một `restrict` cần một ResourceCollection làm nguồn và có thể chứa một hoặc nhiều selector:

```xml
<restrict>
    <fileset dir="src" />
    <name name="**/*.java" />
</restrict>
```

Ví dụ này lấy các tài nguyên do `FileSet` cung cấp dưới thư mục `src`, sau đó chỉ giữ những tài nguyên có tên khớp mẫu `**/*.java`.

Có thể đặt `restrict` trong task `copy`:

```xml
<copy todir="build/java-sources">
    <restrict>
        <fileset dir="src" />
        <name name="**/*.java" />
    </restrict>
</copy>
```

Task `copy` nhận kết quả của `restrict` làm tập nguồn để sao chép. Các tệp không khớp mẫu không được đưa vào tập nguồn của thao tác copy.

Điểm cần nhớ là phần tử `fileset` xác định nơi Ant lấy tài nguyên, còn phần tử `name` xác định tài nguyên nào được giữ. Nếu đổi thư mục nguồn nhưng giữ nguyên selector, quy tắc lọc vẫn có thể được dùng lại với nguồn mới.

## 3. Nhiều selector được kết hợp như thế nào?

Khi đặt nhiều selector trực tiếp trong `restrict`, một tài nguyên phải thỏa mãn tất cả selector mới được giữ lại. Đây là phép kết hợp logic AND.

```xml
<restrict>
    <fileset dir="artifacts" />
    <type type="file" />
    <name name="**/*.jar" />
    <size value="1024" when="more" />
</restrict>
```

Tập kết quả gồm những tài nguyên thỏa mãn đồng thời các điều kiện:

- Tài nguyên là file.
- Tên tài nguyên khớp `**/*.jar`.
- Kích thước lớn hơn 1024 byte.

Nếu tài nguyên là JAR nhưng nhỏ hơn hoặc bằng 1024 byte, nó bị loại. Nếu tài nguyên lớn hơn 1024 byte nhưng không có tên kết thúc bằng `.jar`, nó cũng bị loại.

Để biểu diễn điều kiện OR hoặc phủ định, dùng các selector logic như `or`, `and` và `not`:

```xml
<restrict>
    <fileset dir="docs" />
    <or>
        <name name="**/*.html" />
        <name name="**/*.md" />
    </or>
    <not>
        <name name="**/draft/**" />
    </not>
</restrict>
```

Trong ví dụ này, tài nguyên phải là HTML hoặc Markdown, đồng thời không được nằm dưới một thư mục `draft`. Có thể đọc biểu thức như sau:

```text
(tên khớp **/*.html OR tên khớp **/*.md)
AND
NOT (tên khớp **/draft/**)
```

Các selector logic giúp giữ cấu hình dễ hiểu khi điều kiện có nhiều nhánh. Thay vì cố tạo một mẫu tên rất phức tạp, có thể tách từng tiêu chí thành selector riêng rồi nhóm chúng bằng `and`, `or` hoặc `not`.

## 4. Các ResourceSelector thường dùng

Ant cung cấp các selector để kiểm tra tên, loại, kích thước hoặc nội dung tài nguyên. Một số selector thường gặp:

| Selector | Mục đích | Ví dụ cấu hình |
|---|---|---|
| `name` | Chọn theo tên hoặc mẫu đường dẫn của tài nguyên | `<name name="**/*.xml" />` |
| `type` | Chọn theo loại tài nguyên, chẳng hạn file hoặc directory | `<type type="file" />` |
| `size` | Chọn theo kích thước tài nguyên | `<size value="1024" when="more" />` |
| `contains` | Chọn tài nguyên có nội dung chứa chuỗi chỉ định | `<contains text="production" />` |
| `date` | Chọn theo thời điểm sửa đổi của tài nguyên | `<date datetime="2025-01-01 00:00" when="after" />` |

Các selector có những thuộc tính riêng để mô tả điều kiện. Cần xem tài liệu của selector đang dùng để chọn đúng thuộc tính, đơn vị và cách so sánh. Ví dụ `size` có thể dùng `value` và `when` để xác định ngưỡng; `date` dùng mốc thời gian và hướng so sánh.

Không phải selector nào cũng có thể kiểm tra mọi loại tài nguyên. Selector theo tên cần tài nguyên có tên; selector theo kích thước cần tài nguyên cung cấp kích thước; selector đọc nội dung cần tài nguyên có thể mở để đọc. Khi áp dụng `restrict` lên một ResourceCollection đặc biệt, cần bảo đảm selector tương thích với loại tài nguyên mà collection tạo ra.

## 5. Lọc tài nguyên theo tên và loại

Selector `name` hữu ích khi muốn chọn theo phần mở rộng hoặc cấu trúc thư mục. Ví dụ chỉ lấy các file cấu hình XML:

```xml
<restrict>
    <fileset dir="config" />
    <type type="file" />
    <name name="**/*.xml" />
</restrict>
```

Ở đây `FileSet` cung cấp tài nguyên dưới `config`, `type` loại các tài nguyên không phải file, còn `name` giới hạn kết quả vào các đường dẫn XML.

Có thể kết hợp nhiều loại tên bằng `or`:

```xml
<restrict>
    <fileset dir="config" />
    <type type="file" />
    <or>
        <name name="**/*.yml" />
        <name name="**/*.yaml" />
        <name name="**/*.properties" />
    </or>
</restrict>
```

Selector tên làm việc trên tên tài nguyên do collection cung cấp. Với `FileSet`, tên thường là đường dẫn tương đối so với thư mục gốc của `FileSet`. Vì vậy, nếu `dir="config"`, mẫu `**/*.yml` được so khớp với các tên như `application.yml` hoặc `env/production.yml`.

## 6. Lọc theo kích thước và nội dung

Selector `size` giúp giới hạn tài nguyên theo kích thước. Ví dụ chỉ giữ file lớn hơn 1 KiB (1024 byte):

```xml
<restrict>
    <fileset dir="logs" />
    <type type="file" />
    <size value="1024" when="more" />
</restrict>
```

Thuộc tính `when` xác định quan hệ so sánh với ngưỡng, thường là `more`, `less` hoặc `equal`. Giá trị `value` trong ví dụ được tính bằng byte vì không khai báo đơn vị khác. Hãy chọn ngưỡng phù hợp với mục tiêu lọc và kiểm tra tài liệu Ant tương ứng nếu cần dùng đơn vị kích thước khác.

Selector `contains` có thể được dùng khi cần lọc theo nội dung văn bản:

```xml
<restrict>
    <fileset dir="config" />
    <name name="**/*.properties" />
    <contains text="feature.enabled" casesensitive="false" />
</restrict>
```

Ví dụ này giữ các file properties có chứa chuỗi `feature.enabled`, không phân biệt chữ hoa và chữ thường. Vì selector nội dung phải đọc tài nguyên, việc sử dụng nó có thể tốn chi phí I/O hơn so với lọc chỉ dựa trên tên hoặc metadata.

Với tập tài nguyên lớn, nên áp dụng các tiêu chí rẻ và có khả năng loại bỏ nhiều tài nguyên trước khi cần đọc nội dung. Chẳng hạn, lọc phần mở rộng bằng `name` trước, sau đó mới kiểm tra `contains` trên những tệp còn lại.

## 7. Chia sẻ một restrict bằng id và refid

Nếu nhiều task cần cùng một tập tài nguyên đã lọc, có thể định nghĩa `restrict` một lần với `id`, rồi tham chiếu bằng `refid`:

```xml
<project name="shared-resource-filter" default="copy-config">

    <restrict id="public.config">
        <fileset dir="config" />
        <name name="**/*.properties" />
        <not>
            <name name="**/local/**" />
        </not>
    </restrict>

    <target name="copy-config">
        <copy todir="build/config">
            <restrict refid="public.config" />
        </copy>

        <zip destfile="build/public-config.zip">
            <restrict refid="public.config" />
        </zip>
    </target>

</project>
```

Trong cấu hình này:

- `public.config` là định danh của ResourceCollection đã lọc.
- Collection đầu vào lấy từ thư mục `config`.
- Chỉ tài nguyên có tên khớp `**/*.properties` được giữ.
- Tài nguyên dưới thư mục `local` bị loại.
- Cả `copy` và `zip` đều dùng lại cùng một quy tắc.

Nếu quy tắc thay đổi, chẳng hạn cần loại thêm `**/secret/**`, chỉ cần sửa định nghĩa `public.config`. Những task tham chiếu collection này sẽ nhận cùng thay đổi.

`id` và `refid` giúp chia sẻ một cấu hình, nhưng không làm cho các tài nguyên trở thành cùng một tập vật lý ở mọi thời điểm. ResourceCollection có thể được đánh giá khi task sử dụng nó; kết quả cụ thể phụ thuộc nguồn tài nguyên và thời điểm build chạy.

## 8. Kết hợp restrict với các ResourceCollection khác

Điểm mạnh của `restrict` là nó lọc ResourceCollection, không chỉ riêng `FileSet`. Ví dụ, có thể ghép nhiều nguồn trước rồi lọc tập kết quả bằng một selector chung.

```xml
<restrict>
    <union>
        <fileset dir="module-a/resources" />
        <fileset dir="module-b/resources" />
    </union>
    <name name="**/*.properties" />
</restrict>
```

`union` tạo một ResourceCollection từ các nguồn con; `restrict` giữ lại các tài nguyên có tên khớp `**/*.properties`. Cách tổ chức này hữu ích khi nhiều module cung cấp cùng một loại tài nguyên và task phía sau cần xử lý chúng theo một quy tắc chung.

Một số collection khác có thể đại diện cho nội dung archive hoặc các phần tử classpath. Khi dùng chúng với `restrict`, cần chú ý tên mà collection cung cấp và khả năng selector đọc metadata hoặc nội dung của tài nguyên. Không nên giả định mọi selector hoạt động giống hệt nhau trên file hệ thống, mục trong archive và phần tử classpath.

## 9. Restrict khác gì với include/exclude của FileSet?

`FileSet` đã hỗ trợ `include` và `exclude`. Với một thư mục nguồn thông thường, cấu hình trực tiếp thường ngắn gọn:

```xml
<fileset dir="src">
    <include name="**/*.java" />
    <exclude name="**/generated/**" />
</fileset>
```

`restrict` hữu ích khi muốn biểu diễn bộ lọc dưới dạng ResourceCollection riêng, dùng các ResourceSelector hoặc lọc một collection không phải `FileSet`.

| Nhu cầu | Cách phù hợp |
|---|---|
| Chọn tệp trong một thư mục bằng mẫu đường dẫn đơn giản | `FileSet` với `include` và `exclude` |
| Lọc ResourceCollection bằng nhiều tiêu chí selector | `restrict` |
| Dùng chung một tập tài nguyên đã lọc giữa nhiều task | Định nghĩa `restrict` có `id`, tham chiếu bằng `refid` |
| Ghép tài nguyên từ nhiều nguồn rồi lọc | Collection như `union` kết hợp với `restrict` |
| Chọn theo nội dung hoặc metadata của tài nguyên | `restrict` với selector tương ứng, nếu selector hỗ trợ loại tài nguyên đó |

Không cần bọc mọi `FileSet` trong `restrict`. Hãy chọn cấu trúc đơn giản nhất đáp ứng nhu cầu; dùng `restrict` khi lợi ích của việc tách và tái sử dụng bộ lọc đủ rõ ràng.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Kết quả rỗng dù nguồn có tài nguyên | Selector quá chặt hoặc tên tài nguyên khác mẫu dự kiến | Kiểm tra tên tương đối do ResourceCollection cung cấp và nới điều kiện phù hợp |
| Có tài nguyên khớp một selector nhưng vẫn bị loại | Nhiều selector trực tiếp trong `restrict` được kết hợp theo AND | Kiểm tra từng selector; dùng `or` nếu các điều kiện là lựa chọn thay thế |
| Selector nội dung gây build chậm | Ant phải đọc nhiều tài nguyên để kiểm tra nội dung | Lọc trước bằng tên, loại hoặc metadata rồi mới kiểm tra nội dung |
| `refid` không được tìm thấy | `id` chưa khai báo, sai tên hoặc cấu hình tham chiếu không nằm trong phạm vi project phù hợp | Kiểm tra định danh và vị trí khai báo ResourceCollection |
| Selector không hoạt động trên collection đặc biệt | Loại tài nguyên không cung cấp thông tin mà selector cần | Chọn selector tương thích hoặc chuyển sang collection cung cấp tài nguyên phù hợp |
| Mẫu tên không khớp đường dẫn mong muốn | Mẫu được so khớp với tên resource, có thể khác đường dẫn tuyệt đối trên máy | Kiểm tra tên tương đối từ collection và dùng mẫu theo đúng cấu trúc đó |
| Dùng restrict cho một FileSet đơn giản làm cấu hình khó đọc hơn | Bộ lọc chưa cần tách thành ResourceCollection riêng | Dùng trực tiếp include/exclude trong FileSet nếu chỉ cần lọc theo mẫu đường dẫn |

Khi kết quả không đúng, hãy xác minh nguồn ResourceCollection trước, sau đó kiểm tra tên và metadata thực tế của resource, rồi xem từng selector. Với nhiều selector, kiểm tra điều kiện AND/OR và phủ định thường giúp tìm ra lý do tài nguyên bị loại.

## 11. Trình tự xây dựng bộ lọc tài nguyên

Khi cần giới hạn tài nguyên trong buildfile, có thể tiến hành theo trình tự sau:

1. Xác định task cuối cùng cần nhận những tài nguyên nào và nguồn của chúng là gì.
2. Chọn ResourceCollection phù hợp, chẳng hạn `fileset`, `zipfileset`, `path` hoặc một collection kết hợp.
3. Chọn selector dựa trên tiêu chí thực tế: tên, loại, kích thước, ngày tháng hoặc nội dung.
4. Đặt các selector trực tiếp nếu tất cả phải đúng; dùng `and`, `or` và `not` để thể hiện logic rõ ràng.
5. Nếu nhiều task cần cùng tập đã lọc, định nghĩa `restrict` có `id` và tham chiếu bằng `refid`.
6. Kiểm tra tính tương thích của selector với loại tài nguyên và cân nhắc chi phí khi selector phải đọc nội dung.
7. Chạy target trên dữ liệu đại diện và kiểm tra danh sách hoặc artifact đầu ra để xác nhận tập tài nguyên được chọn.

`restrict` cho phép tách nguồn tài nguyên khỏi logic chọn tài nguyên. ResourceCollection cung cấp các ứng viên, ResourceSelector mô tả điều kiện giữ lại, còn `restrict` tạo ra tập con để task tiếp theo sử dụng. Khi cần chia sẻ bộ lọc, `id` và `refid` giúp các bước build dùng chung một định nghĩa và giữ quy tắc chọn tài nguyên nhất quán.
