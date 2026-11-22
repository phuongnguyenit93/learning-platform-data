# Ánh xạ tên bằng globmapper, regexpmapper, flattenmapper và các mapper kết hợp

Trong Apache Ant, nhiều thao tác tệp cần chọn nguồn rồi xác định tên hoặc đường dẫn đích. Ví dụ, khi sao chép mã nguồn, bạn có thể muốn đổi phần mở rộng `.java` thành `.java.bak`; khi gom báo cáo từ nhiều thư mục, bạn có thể muốn bỏ phần đường dẫn thư mục; hoặc khi tạo nhiều bản sao theo các quy tắc tên khác nhau, bạn cần áp dụng nhiều phép ánh xạ cho cùng một tệp.

Ant giải quyết việc này bằng **mapper**. Mapper nhận tên đường dẫn nguồn và trả về một hoặc nhiều tên đường dẫn đích. Các mapper thường được lồng trong task như `copy` hoặc `move`, nơi Ant thực hiện thao tác tệp sau khi tính tên đích.

Bài học này trình bày các mapper thường dùng: `globmapper`, `regexpmapper`, `flattenmapper`, cùng hai cách kết hợp mapper là `chainedmapper` và `compositemapper`. Bạn cũng sẽ thấy cách chọn mapper phù hợp, cách tránh xung đột tên và cách kiểm tra kết quả ánh xạ.

## 1. Mapper là gì?

Một mapper mô tả quy tắc chuyển đổi từ tên tệp nguồn sang tên tệp đích. Bản thân mapper chỉ quyết định tên đích; task chứa mapper mới thực hiện việc sao chép, di chuyển hoặc xử lý tệp.

Ví dụ, dự án có:

```text
project/
├── src/
│   ├── Main.java
│   └── com/example/Service.java
└── dist/
```

Nếu muốn sao chép các tệp Java sang thư mục `dist` và đổi đuôi thành `.java.bak`, mapper có thể tạo các tên đích:

| Tên nguồn tương đối | Tên đích được ánh xạ |
|---|---|
| `Main.java` | `Main.java.bak` |
| `com/example/Service.java` | `com/example/Service.java.bak` |

Trong task `copy`, `fileset` quyết định những tệp nguồn nào được chọn, còn mapper quyết định tên đích tương ứng. Hai việc này độc lập:

- `include` và `exclude` lọc tập tệp nguồn.
- Mapper biến đổi tên đường dẫn của các tệp đã chọn.
- `copy` hoặc `move` thực hiện thao tác trên hệ thống tệp.

Một mapper thường được khai báo bên trong task:

```xml
<copy todir="dist">
    <fileset dir="src">
        <include name="**/*.java"/>
    </fileset>
    <mapper>
        <globmapper from="*.java" to="*.java.bak"/>
    </mapper>
</copy>
```

`todir` là thư mục gốc đích. Tên mà mapper trả về được đặt bên dưới thư mục này, giữ lại các thành phần đường dẫn mà quy tắc ánh xạ không loại bỏ.

## 2. globmapper: ánh xạ bằng mẫu glob

`globmapper` dùng mẫu `from` và `to` để thay đổi tên tệp. Đây là lựa chọn đơn giản khi quy tắc đổi tên có cấu trúc rõ ràng, chẳng hạn đổi phần mở rộng hoặc thêm hậu tố.

Cú pháp cơ bản:

```xml
<mapper>
    <globmapper from="*.java" to="*.class"/>
</mapper>
```

Phần `*` trong mẫu nguồn đại diện cho phần tên được giữ lại và đưa vào vị trí `*` trong mẫu đích. Với ví dụ trên:

| Nguồn | Đích |
|---|---|
| `Main.java` | `Main.class` |
| `Service.java` | `Service.class` |

Có thể thêm hậu tố:

```xml
<mapper>
    <globmapper from="*.txt" to="*.txt.bak"/>
</mapper>
```

Ví dụ sử dụng trong task `copy`:

```xml
<project name="glob-mapper-demo" default="backup">

    <target name="backup">
        <mkdir dir="dist"/>

        <copy todir="dist">
            <fileset dir="src">
                <include name="**/*.txt"/>
            </fileset>
            <mapper>
                <globmapper from="*.txt" to="*.txt.bak"/>
            </mapper>
        </copy>
    </target>

</project>
```

Nếu `src/docs/readme.txt` là nguồn, tên đích tương ứng sẽ là `dist/docs/readme.txt.bak`. Mapper xử lý tên tương đối trong tập nguồn; `todir` cung cấp thư mục gốc đích.

### Khi nào dùng globmapper?

Hãy dùng `globmapper` khi quy tắc đổi tên đơn giản và có thể diễn đạt bằng phần tên khớp với `*`, ví dụ:

- Thêm hoặc đổi phần mở rộng.
- Thêm tiền tố hoặc hậu tố.
- Chuyển một nhóm tệp theo cùng một quy tắc đặt tên.

Nếu quy tắc cần nhiều nhóm bắt giữ, kiểm tra cấu trúc tên phức tạp hoặc chuyển đổi dựa trên biểu thức chính quy, hãy cân nhắc `regexpmapper`.

## 3. regexpmapper: ánh xạ bằng biểu thức chính quy

`regexpmapper` dùng regular expression để mô tả mẫu tên nguồn và các nhóm bắt giữ để xây dựng tên đích. Nó phù hợp khi quy tắc đổi tên phức tạp hơn một phép thay thế bằng `*`.

Ví dụ, đổi phần mở rộng `.java` thành `.class`:

```xml
<mapper>
    <regexpmapper
        from="^(.*)\.java$"
        to="\1.class"/>
</mapper>
```

Giải thích:

- `^` đánh dấu đầu chuỗi.
- `(.*)` bắt giữ phần tên đường dẫn.
- `\.` khớp dấu chấm thật trước phần mở rộng.
- `java$` yêu cầu chuỗi kết thúc bằng `.java`.
- `\1` trong mẫu đích tham chiếu nhóm bắt giữ thứ nhất.

Kết quả:

| Nguồn | Đích |
|---|---|
| `Main.java` | `Main.class` |
| `com/example/Service.java` | `com/example/Service.class` |

Có thể đổi quy ước tên phức tạp hơn. Ví dụ, thêm tiền tố `compiled-` cho các tệp `.xml`:

```xml
<mapper>
    <regexpmapper
        from="^(.*)\.xml$"
        to="compiled-\1.xml"/>
</mapper>
```

Với nguồn `config/app.xml`, tên được ánh xạ là `compiled-config/app.xml`.

### Nhóm bắt giữ và mẫu thay thế

Nếu biểu thức có nhiều nhóm, có thể tham chiếu từng nhóm trong mẫu đích:

```xml
<mapper>
    <regexpmapper
        from="^([a-z]+)-([0-9]+)\.log$"
        to="archive/\2/\1.log"/>
</mapper>
```

Ví dụ:

| Nguồn | Nhóm 1 | Nhóm 2 | Đích |
|---|---|---|---|
| `service-2026.log` | `service` | `2026` | `archive/2026/service.log` |
| `worker-17.log` | `worker` | `17` | `archive/17/worker.log` |

Khi viết regular expression trong XML, dấu gạch chéo ngược `\` không cần escape theo quy tắc chuỗi Java vì đây là giá trị thuộc tính XML. Tuy vậy, biểu thức vẫn phải tuân theo cú pháp regex mà mapper của phiên bản Ant sử dụng. Hãy kiểm tra kỹ các ký tự đặc biệt và dấu phân cách khi đổi tên đường dẫn.

### Chú ý khi dùng regexpmapper

- Neo biểu thức bằng `^` và `$` khi muốn khớp toàn bộ tên nguồn, tránh ánh xạ ngoài dự kiến.
- Dùng `\.` khi muốn khớp dấu chấm thật trong phần mở rộng.
- Đặt nhóm bắt giữ rõ ràng để mẫu đích dễ đọc.
- Kiểm tra trường hợp tên nguồn không khớp regex; mapper có thể không tạo tên đích cho trường hợp đó.
- Không dùng biểu thức quá rộng nếu nhiều tên nguồn có thể bị ánh xạ về cùng một đích.

## 4. flattenmapper: bỏ phần đường dẫn thư mục

`flattenmapper` loại bỏ các thành phần thư mục khỏi tên đường dẫn nguồn và chỉ giữ lại tên tệp cuối cùng.

Ví dụ:

| Nguồn | Kết quả |
|---|---|
| `src/com/example/Main.java` | `Main.java` |
| `reports/2026/test.xml` | `test.xml` |
| `docs/setup/readme.txt` | `readme.txt` |

Khai báo:

```xml
<mapper>
    <flattenmapper/>
</mapper>
```

Ví dụ gom tất cả báo cáo XML từ các thư mục con vào một thư mục:

```xml
<copy todir="dist/reports">
    <fileset dir="reports">
        <include name="**/*.xml"/>
    </fileset>
    <mapper>
        <flattenmapper/>
    </mapper>
</copy>
```

Với mapper này, `reports/unit/test.xml` và `reports/integration/test.xml` đều được ánh xạ thành `test.xml` trong `dist/reports`.

### Rủi ro trùng tên khi flatten

Việc loại bỏ thư mục có thể làm nhiều tệp nguồn có cùng basename ánh xạ đến cùng một tên đích. Ví dụ:

```text
reports/
├── unit/test.xml
└── integration/test.xml
```

Cả hai đều trở thành `test.xml`. Khi đó, task có thể ghi đè hoặc gặp xung đột tùy cách thực hiện và cấu hình. Không nên dựa vào thứ tự quét để quyết định nội dung nào được giữ lại.

Trước khi dùng `flattenmapper`, hãy bảo đảm tên tệp là duy nhất hoặc chọn một quy tắc khác giữ lại thông tin phân biệt, chẳng hạn giữ một phần cấu trúc thư mục bằng mapper phù hợp.

## 5. Các mapper thường gặp khác

Ngoài ba mapper chính, Ant còn cung cấp một số mapper hữu ích:

| Mapper | Công dụng |
|---|---|
| `identitymapper` | Giữ nguyên tên đường dẫn nguồn |
| `mergemapper` | Ánh xạ nhiều tên nguồn về một tên đích cố định |
| `packagemapper` | Chuyển đổi tên package Java dạng đường dẫn thành dạng package phù hợp theo quy tắc mapper |
| `unpackagemapper` | Chuyển đổi tên package dạng dấu chấm thành cấu trúc đường dẫn |
| `chainedmapper` | Đưa kết quả của mapper trước vào mapper tiếp theo |
| `compositemapper` | Kết hợp kết quả của nhiều mapper áp dụng độc lập lên cùng tên nguồn |

Ví dụ `identitymapper`:

```xml
<mapper>
    <identitymapper/>
</mapper>
```

Mapper này trả lại tên nguồn như cũ. Nó hữu ích khi cần khai báo mapper trong cấu hình dùng chung nhưng một nhánh xử lý không cần đổi tên.

Ví dụ `mergemapper`:

```xml
<mapper>
    <mergemapper to="all-reports.xml"/>
</mapper>
```

Các nguồn được ánh xạ về cùng tên `all-reports.xml`. Mapper chỉ xác định tên đích; việc nội dung được nối, ghi đè hay xử lý theo cách nào phụ thuộc vào task đang sử dụng mapper. Không nên giả định `mergemapper` tự hợp nhất nội dung tệp.

## 6. chainedmapper: kết hợp tuần tự

`chainedmapper` thực hiện một chuỗi phép ánh xạ. Kết quả của mapper thứ nhất trở thành đầu vào của mapper thứ hai, rồi tiếp tục theo thứ tự khai báo.

Ví dụ, muốn:

1. Bỏ các thư mục để chỉ còn basename.
2. Đổi phần mở rộng `.java` thành `.class`.

Có thể viết:

```xml
<mapper>
    <chainedmapper>
        <flattenmapper/>
        <globmapper from="*.java" to="*.class"/>
    </chainedmapper>
</mapper>
```

Với nguồn `src/com/example/Main.java`, quá trình diễn ra:

```text
src/com/example/Main.java
          |
          v
flattenmapper
          |
          v
Main.java
          |
          v
globmapper (*.java -> *.class)
          |
          v
Main.class
```

Ví dụ sử dụng:

```xml
<copy todir="dist/classes">
    <fileset dir="src">
        <include name="**/*.java"/>
    </fileset>
    <mapper>
        <chainedmapper>
            <flattenmapper/>
            <globmapper from="*.java" to="*.class"/>
        </chainedmapper>
    </mapper>
</copy>
```

Kết quả của các tệp nguồn được đưa trực tiếp vào `dist/classes` dưới dạng basename đã đổi đuôi. Nếu hai package có cùng tên lớp, kết quả sẽ trùng tên; chỉ dùng cách này khi việc làm phẳng cấu trúc là chủ đích.

### Thứ tự trong chainedmapper rất quan trọng

Hai chuỗi dưới đây không tương đương:

```xml
<chainedmapper>
    <flattenmapper/>
    <globmapper from="*.java" to="*.class"/>
</chainedmapper>
```

và:

```xml
<chainedmapper>
    <globmapper from="*.java" to="*.class"/>
    <flattenmapper/>
</chainedmapper>
```

Chuỗi đầu tiên bỏ thư mục trước, sau đó đổi đuôi. Chuỗi thứ hai đổi đuôi khi tên còn chứa đường dẫn, rồi mới bỏ thư mục. Với ví dụ đơn giản, cả hai có thể cho kết quả cuối giống nhau, nhưng với pattern phụ thuộc thư mục hoặc quy tắc phức tạp hơn, thứ tự sẽ quyết định mapper sau nhận được tên gì.

Hãy mô tả từng bước đầu vào và đầu ra khi xây dựng chuỗi để tránh sai lệch.

## 7. compositemapper: kết hợp nhiều kết quả song song

`compositemapper` cũng chứa nhiều mapper, nhưng cách kết hợp khác `chainedmapper`. Mỗi mapper con được áp dụng độc lập lên tên nguồn ban đầu; các kết quả được ghép thành danh sách kết quả ánh xạ.

Ví dụ, muốn tạo hai bản sao từ mỗi tệp Java:

- Một bản giữ cấu trúc thư mục và thêm hậu tố `.bak`.
- Một bản chỉ giữ basename.

Khai báo:

```xml
<mapper>
    <compositemapper>
        <globmapper from="*.java" to="*.java.bak"/>
        <flattenmapper/>
    </compositemapper>
</mapper>
```

Với nguồn `src/com/example/Main.java`, hai kết quả là:

| Mapper con | Tên đích |
|---|---|
| `globmapper` | `src/com/example/Main.java.bak` |
| `flattenmapper` | `Main.java` |

Trong task `copy`, cần bật `enablemultiplemappings="true"` nếu muốn sử dụng tất cả kết quả do composite mapper trả về:

```xml
<copy todir="dist" enablemultiplemappings="true">
    <fileset dir="src">
        <include name="**/*.java"/>
    </fileset>
    <mapper>
        <compositemapper>
            <globmapper from="*.java" to="*.java.bak"/>
            <flattenmapper/>
        </compositemapper>
    </mapper>
</copy>
```

Thuộc tính `enablemultiplemappings` của task `copy` mặc định là `false`. Khi để mặc định, task chỉ sử dụng một ánh xạ cho mỗi tệp nguồn. Đặt `true` khi bạn thực sự muốn copy một nguồn đến nhiều tên đích. Hãy kiểm tra tài liệu của task khác nếu dùng composite mapper ngoài `copy`, vì cơ chế xử lý nhiều kết quả phụ thuộc vào task đó.

### Phân biệt chainedmapper và compositemapper

| Tiêu chí | `chainedmapper` | `compositemapper` |
|---|---|---|
| Cách xử lý | Tuần tự | Song song trên tên nguồn ban đầu |
| Đầu vào của mapper sau | Kết quả mapper trước | Tên nguồn ban đầu |
| Kết quả | Chuỗi biến đổi tiếp nối nhau | Danh sách kết quả từ các mapper con |
| Mục đích | Nhiều bước đổi tên liên tiếp | Tạo nhiều tên đích từ cùng một nguồn |
| Ví dụ | Flatten rồi đổi phần mở rộng | Tạo bản backup và bản flatten |

Đây là khác biệt quan trọng nhất khi lựa chọn mapper kết hợp. Nếu cần chuyển đổi qua nhiều bước, dùng chained; nếu cần nhiều kết quả độc lập, dùng composite.

## 8. Mapper generic và mapper lồng trong task

Ant cho phép khai báo mapper theo tên loại hoặc dùng mapper chuyên biệt. Ví dụ dùng generic mapper với thuộc tính `type`:

```xml
<copy todir="dist">
    <fileset dir="src">
        <include name="**/*.java"/>
    </fileset>
    <mapper type="glob" from="*.java" to="*.java.bak"/>
</copy>
```

Cách này ngắn gọn khi chỉ dùng một mapper đơn giản. Khi cần kết hợp mapper hoặc muốn build file diễn đạt rõ loại mapper, có thể dùng phần tử chuyên biệt:

```xml
<copy todir="dist">
    <fileset dir="src">
        <include name="**/*.java"/>
    </fileset>
    <mapper>
        <globmapper from="*.java" to="*.java.bak"/>
    </mapper>
</copy>
```

Các mapper kết hợp thường được lồng bên trong `<mapper>` để task nhận một cấu hình mapper duy nhất:

```xml
<mapper>
    <chainedmapper>
        <flattenmapper/>
        <globmapper from="*.txt" to="*.txt.bak"/>
    </chainedmapper>
</mapper>
```

Tên phần tử và thuộc tính phải đúng với loại mapper và task đang dùng. Không phải task nào cũng hỗ trợ mọi mapper hoặc mọi thuộc tính; hãy đối chiếu tài liệu của task trước khi dùng cấu hình nâng cao.

## 9. Kết hợp mapper với fileset và task copy/move

Mapper không tự tìm tệp. Tập nguồn thường được xác định bằng `fileset`, sau đó mapper biến đổi tên của từng tệp đã chọn.

Ví dụ sao chép file cấu hình sang một cấu trúc phát hành:

```xml
<target name="copy-config">
    <copy todir="dist/config">
        <fileset dir="src">
            <include name="**/*.yml"/>
            <exclude name="**/local-*.yml"/>
        </fileset>
        <mapper>
            <regexpmapper
                from="^(.*)\.yml$"
                to="\1.production.yml"/>
        </mapper>
    </copy>
</target>
```

Fileset chỉ chọn các tệp YAML và loại cấu hình local. Mapper giữ toàn bộ đường dẫn tương đối trước phần mở rộng, rồi thêm hậu tố `.production`; cách này cũng xử lý được tệp YAML nằm ngay tại thư mục gốc của fileset.

Với task `move`, cách khai báo mapper tương tự:

```xml
<move todir="archive">
    <fileset dir="reports">
        <include name="**/*.xml"/>
    </fileset>
    <mapper>
        <flattenmapper/>
    </mapper>
</move>
```

Task `move` di chuyển nguồn sang tên đích đã ánh xạ. Hãy cẩn thận với `flattenmapper` vì nhiều nguồn có thể cùng tên đích; thao tác di chuyển có thể làm mất hoặc ghi đè dữ liệu nếu không xử lý xung đột trước.

## 10. Xử lý nhiều ánh xạ và xung đột tên

Một mapper có thể không trả về tên đích nào nếu tên nguồn không khớp quy tắc. Một mapper khác có thể trả về nhiều tên đích. Ngoài ra, nhiều tệp nguồn khác nhau có thể cùng được ánh xạ về một tên đích.

Trước khi chạy task trên toàn bộ dự án, hãy kiểm tra các tình huống:

- **Không khớp:** nguồn không phù hợp với `from` hoặc regex, do đó không có tên đích theo quy tắc đó.
- **Nhiều kết quả:** composite mapper trả về nhiều đường dẫn cho một nguồn; task phải cho phép multiple mappings.
- **Đích trùng nhau:** hai nguồn khác nhau cùng ánh xạ về một tên đích, thường gặp với `flattenmapper` hoặc `mergemapper`.
- **Đích ngoài ý muốn:** biểu thức regex hoặc glob quá rộng khiến đường dẫn bị đổi khác dự kiến.
- **Đường dẫn đích không hợp lệ:** mẫu thay thế tạo tên có ký tự hoặc cấu trúc không phù hợp với hệ điều hành.

Để giảm rủi ro:

1. Bắt đầu với một fileset nhỏ có vài tệp đại diện.
2. Viết ra tên nguồn tương đối và tên đích dự kiến cho từng mapper.
3. Kiểm tra riêng mapper trước khi kết hợp chúng.
4. Bảo đảm kết quả đích duy nhất nếu task không có chủ đích ghi nhiều nguồn vào một nơi.
5. Chỉ bật `enablemultiplemappings` khi muốn một nguồn tạo nhiều bản sao.
6. Không dùng `flattenmapper` nếu basename không duy nhất.

## 11. Chẩn đoán khi mapper không cho kết quả mong đợi

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tệp được copy nhưng tên không đổi | Mapper không khớp tên nguồn hoặc task không dùng mapper như dự kiến | Kiểm tra `from`, `to` và vị trí khai báo mapper |
| Không có tệp đích | Pattern hoặc regex không khớp; fileset không chọn được nguồn | Kiểm tra `include`, `exclude` và đường dẫn tương đối |
| Chỉ có một trong nhiều tên đích | `enablemultiplemappings` đang ở giá trị mặc định `false` hoặc task chỉ dùng một mapping | Kiểm tra hỗ trợ multiple mappings của task và bật khi cần |
| Tệp bị ghi đè sau flatten | Nhiều nguồn có cùng basename | Giữ lại thư mục trong tên đích hoặc tạo quy tắc tên duy nhất |
| Regex không đổi phần tên như mong muốn | Nhóm bắt giữ hoặc tham chiếu `\1`, `\2` sai | Kiểm tra biểu thức, dấu neo và thứ tự nhóm |
| Kết quả chainedmapper sai | Thứ tự mapper không đúng hoặc mapper sau không khớp đầu ra mapper trước | Theo dõi đầu ra trung gian sau từng mapper |
| Đường dẫn đích bị lặp hoặc thiếu thư mục | Nhầm đường dẫn tương đối với `todir` hoặc flatten | Tính tên mapper trả về trước khi ghép với thư mục đích |

Một cách thực hành tốt là thử từng mapper riêng trong một target thử nghiệm, sau đó mới chuyển sang chained hoặc composite mapper. Khi kết quả không đúng, việc tách từng bước giúp xác định chính xác mapper nào tạo ra tên ngoài dự kiến.

## 12. Ghi nhớ

- Mapper biến đổi tên đường dẫn nguồn thành tên đường dẫn đích; task như `copy` hoặc `move` mới thực hiện thao tác tệp.
- `globmapper` phù hợp với quy tắc đổi tên đơn giản bằng pattern `from` và `to`.
- `regexpmapper` dùng biểu thức chính quy và nhóm bắt giữ để xây dựng tên đích linh hoạt.
- `flattenmapper` bỏ phần thư mục và chỉ giữ basename; cần đề phòng các nguồn trùng tên.
- `chainedmapper` áp dụng mapper tuần tự, đầu ra của bước trước là đầu vào của bước sau.
- `compositemapper` áp dụng các mapper con độc lập lên cùng nguồn và kết hợp các kết quả.
- Với task `copy`, `enablemultiplemappings="true"` cho phép sử dụng nhiều tên đích do mapper trả về.
- Fileset lọc nguồn; mapper đổi tên; task thực hiện copy hoặc move.
- Luôn kiểm tra tên đích và xung đột trước khi áp dụng mapper lên toàn bộ cây thư mục.

Khi cần đổi tên tệp trong build, hãy chọn mapper theo cấu trúc của phép biến đổi: glob cho mẫu đơn giản, regex cho quy tắc phức tạp, flatten để bỏ thư mục, chained cho nhiều bước nối tiếp và composite khi một nguồn cần tạo nhiều kết quả độc lập.
