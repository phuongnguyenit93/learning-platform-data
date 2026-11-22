# Xử lý luồng văn bản bằng FilterChain

Trong Apache Ant, `FilterChain` cho phép biến đổi nội dung văn bản khi một task đọc và ghi dữ liệu. Bạn có thể nối nhiều filter để lọc dòng, thay token, mở rộng property, chuẩn hóa khoảng trắng, thêm tiền tố hoặc chỉ lấy một phần nội dung. Các filter được thực thi theo thứ tự khai báo, vì vậy một chuỗi filter có thể thực hiện nhiều bước xử lý liên tiếp trong cùng một thao tác.

`FilterChain` thường được dùng với các task như `<copy>`, `<loadfile>`, `<loadproperties>`, `<loadresource>`, `<concat>` và `<move>`. Cách này giúp build file xử lý nội dung văn bản trong quá trình build mà không cần viết một chương trình phụ cho từng phép biến đổi.

## 1. FilterChain là gì?

`<filterchain>` là một datatype chứa một chuỗi các filter reader. Mỗi filter nhận luồng ký tự từ bước trước, thực hiện một phép biến đổi rồi chuyển kết quả cho filter tiếp theo. Filter cuối cùng cung cấp nội dung đã xử lý cho task đang sử dụng FilterChain.

Ví dụ về một chuỗi xử lý:

```text
Tệp văn bản nguồn
       |
       v
  HeadFilter
       |
       v
  LineContains
       |
       v
  PrefixLines
       |
       v
Tệp văn bản đầu ra
```

Với chuỗi trên, Ant lấy một số dòng đầu tiên, giữ lại các dòng thỏa điều kiện rồi thêm tiền tố cho từng dòng còn lại.

FilterChain không phải task độc lập. Nó là cấu hình lồng bên trong một task có hỗ trợ xử lý luồng văn bản. Task chịu trách nhiệm đọc nguồn, đưa nội dung qua chuỗi filter và ghi hoặc lưu kết quả.

## 2. Cú pháp cơ bản

Ví dụ dùng FilterChain bên trong task `<copy>`:

```xml
<copy file="input.txt" tofile="build/output.txt">
    <filterchain>
        <prefixlines prefix="[BUILD] "/>
    </filterchain>
</copy>
```

Task `<copy>` đọc `input.txt`, chuyển từng dòng qua filter `prefixlines`, sau đó ghi nội dung đã biến đổi vào `build/output.txt`. Mỗi dòng nhận thêm chuỗi `[BUILD] ` ở đầu.

Một FilterChain có thể chứa nhiều filter:

```xml
<filterchain>
    <headfilter lines="100"/>
    <linecontains>
        <contains value="ERROR"/>
    </linecontains>
    <prefixlines prefix="[LOG] "/>
</filterchain>
```

Các filter được áp dụng lần lượt từ trên xuống dưới. Đổi thứ tự filter có thể làm kết quả khác nhau. Trong ví dụ, `headfilter` giới hạn đầu vào còn 100 dòng trước khi `linecontains` lọc những dòng có `ERROR`; cuối cùng `prefixlines` thêm tiền tố cho các dòng được giữ lại.

### 2.1. Task hỗ trợ FilterChain

Theo tài liệu Apache Ant, các task tích hợp hỗ trợ nested `<filterchain>` gồm:

| Task | Cách dùng FilterChain |
|---|---|
| `<copy>` | Biến đổi nội dung tệp khi sao chép sang vị trí khác |
| `<move>` | Biến đổi nội dung trong thao tác di chuyển tệp |
| `<loadfile>` | Đọc nội dung đã lọc vào một Ant property |
| `<loadproperties>` | Lọc nội dung trước khi nạp các cặp key-value thành property |
| `<loadresource>` | Đọc resource và lưu nội dung đã lọc vào property |
| `<concat>` | Ghép nội dung từ các resource với bước lọc |

Không phải task nào cũng chấp nhận `<filterchain>`. Hãy xem tài liệu của task đang dùng trước khi thêm phần tử lồng. Nếu task không hỗ trợ datatype này, Ant sẽ báo lỗi cấu hình thay vì tự áp dụng filter.

### 2.2. Dùng FilterChain với `loadfile`

`<loadfile>` đọc nội dung một tệp và lưu kết quả vào property. Khi có FilterChain, nội dung được biến đổi trước khi property nhận giá trị:

```xml
<loadfile srcfile="README.txt" property="readme.preview">
    <filterchain>
        <headfilter lines="5"/>
    </filterchain>
</loadfile>

<echo message="${readme.preview}"/>
```

Ví dụ lưu năm dòng đầu của `README.txt` vào `readme.preview`. Task `<echo>` sau đó hiển thị nội dung property. Đây là cách thuận tiện để lấy một phần nội dung tệp phục vụ thông báo hoặc xử lý tiếp theo trong build.

## 3. Các filter thường dùng

Ant cung cấp nhiều filter reader dựng sẵn. Một số filter có cú pháp ngắn, ví dụ `<headfilter/>`; cú pháp này tương đương với việc khai báo một `<filterreader>` trỏ đến lớp triển khai của filter.

| Filter | Công dụng |
|---|---|
| `headfilter` | Lấy một số dòng đầu, có thể bỏ qua một số dòng ban đầu |
| `tailfilter` | Lấy một số dòng cuối, có thể bỏ qua một số dòng ở cuối |
| `linecontains` | Chỉ giữ các dòng chứa chuỗi chỉ định |
| `linecontainsregexp` | Chỉ giữ các dòng khớp biểu thức chính quy |
| `replacetokens` | Thay token được đánh dấu trong nội dung bằng giá trị cấu hình |
| `expandproperties` | Thay biểu thức `${property}` trong nội dung bằng giá trị Ant property |
| `prefixlines`, `suffixlines` | Thêm tiền tố hoặc hậu tố cho từng dòng |
| `striplinecomments` | Bỏ các dòng bắt đầu bằng chuỗi chú thích được khai báo |
| `stripjavacomments` | Loại bỏ comment theo cú pháp Java |
| `striplinebreaks` | Xóa các ký tự xuống dòng được chỉ định |
| `tabstospaces` | Thay ký tự tab bằng số dấu cách xác định |
| `sortfilter` | Sắp xếp các dòng trong luồng |
| `tokenfilter` | Tách nội dung thành token rồi lọc hoặc thay đổi từng token |

Không phải filter nào cũng phù hợp với mọi loại dữ liệu. Ví dụ, `stripjavacomments` hiểu comment theo cú pháp Java, còn `striplinecomments` chỉ loại bỏ những dòng bắt đầu bằng chuỗi chú thích đã khai báo.

## 4. Lọc dòng theo nội dung

### 4.1. `linecontains`

`linecontains` giữ lại những dòng có chứa chuỗi được chỉ định. Ví dụ:

```xml
<copy file="application.log" tofile="build/errors.log">
    <filterchain>
        <linecontains>
            <contains value="ERROR"/>
        </linecontains>
    </filterchain>
</copy>
```

Chỉ những dòng chứa chuỗi `ERROR` được ghi vào `build/errors.log`. Các dòng khác bị loại khỏi luồng.

Có thể khai báo nhiều chuỗi cần tìm:

```xml
<linecontains>
    <contains value="ERROR"/>
    <contains value="database"/>
</linecontains>
```

Mặc định, một dòng phải chứa tất cả các chuỗi đã khai báo mới được giữ lại. Từ Ant 1.10.4, thuộc tính `matchAny="true"` thay đổi quy tắc thành chỉ cần chứa ít nhất một chuỗi:

```xml
<linecontains matchAny="true">
    <contains value="ERROR"/>
    <contains value="WARN"/>
</linecontains>
```

Thuộc tính `negate="true"` đảo điều kiện, nghĩa là giữ các dòng không khớp:

```xml
<linecontains negate="true">
    <contains value="DEBUG"/>
</linecontains>
```

Ví dụ này loại các dòng chứa `DEBUG`, chỉ giữ những dòng còn lại.

### 4.2. `linecontainsregexp`

Nếu cần lọc theo mẫu phức tạp hơn, dùng `linecontainsregexp`:

```xml
<copy file="application.log" tofile="build/http-errors.log">
    <filterchain>
        <linecontainsregexp>
            <regexp pattern="HTTP/[0-9.]+ 5[0-9][0-9]"/>
        </linecontainsregexp>
    </filterchain>
</copy>
```

Mẫu trên chọn những dòng có mã trạng thái HTTP thuộc nhóm 500. Có thể dùng `negate="true"` để giữ các dòng không khớp. Mặc định phép so khớp phân biệt chữ hoa và chữ thường; thuộc tính `casesensitive` cho phép điều chỉnh điều này.

Từ Ant 1.10.2, `regexp` có thể được khai báo trực tiếp dưới dạng thuộc tính `regexp` của `linecontainsregexp`. Với phiên bản cũ hơn, dùng nested `<regexp pattern="..."/>` như ví dụ trên để tương thích với cú pháp được hỗ trợ rộng hơn.

## 5. Thay token trong nội dung bằng `replacetokens`

`replacetokens` thay những token nằm giữa dấu mở và dấu đóng bằng các giá trị được khai báo. Mặc định, token dùng dấu `@` ở hai đầu, ví dụ `@APP_NAME@`.

Giả sử tệp mẫu `app.properties.template` có nội dung:

```properties
app.name=@APP_NAME@
app.version=@APP_VERSION@
app.environment=@ENVIRONMENT@
```

Build file có thể thay các token bằng Ant property:

```xml
<project name="filterchain-demo" default="prepare-config" basedir=".">
    <property name="app.name" value="inventory"/>
    <property name="app.version" value="2.4.0"/>
    <property name="environment" value="staging"/>

    <target name="prepare-config">
        <copy file="app.properties.template"
              tofile="build/app.properties">
            <filterchain>
                <replacetokens>
                    <token key="APP_NAME" value="${app.name}"/>
                    <token key="APP_VERSION" value="${app.version}"/>
                    <token key="ENVIRONMENT" value="${environment}"/>
                </replacetokens>
            </filterchain>
        </copy>
    </target>
</project>
```

Kết quả trong `build/app.properties`:

```properties
app.name=inventory
app.version=2.4.0
app.environment=staging
```

### 5.1. Thay đổi dấu token

Nếu nội dung mẫu dùng dấu `{{` và `}}`, có thể khai báo dấu mở và đóng riêng:

```xml
<replacetokens begintoken="{{" endtoken="}}">
    <token key="APP_NAME" value="${app.name}"/>
</replacetokens>
```

Khi đó chuỗi `{{APP_NAME}}` được thay bằng giá trị của `${app.name}`.

### 5.2. Đọc token từ properties file

Nếu có nhiều token, có thể lưu các cặp key-value trong tệp properties riêng:

```properties
APP_NAME=inventory
APP_VERSION=2.4.0
ENVIRONMENT=staging
```

Với dạng FilterReader tổng quát, có thể nạp trực tiếp tệp properties bằng tham số `propertiesfile`:

```xml
<copy file="app.properties.template" tofile="build/app.properties">
    <filterchain>
        <filterreader classname="org.apache.tools.ant.filters.ReplaceTokens">
            <param type="propertiesfile" value="tokens.properties"/>
        </filterreader>
    </filterchain>
</copy>
```

Tệp `tokens.properties` chứa các cặp như `APP_NAME=inventory` và `APP_VERSION=2.4.0`. Trong cú pháp tiện lợi `<replacetokens>`, có thể dùng thuộc tính `propertiesResource` để đọc các token từ một Ant resource. Khi số lượng token lớn hoặc thay đổi theo môi trường, hãy tách bảng thay thế thành tệp được quản lý riêng để dễ cập nhật.

## 6. Mở rộng Ant property trong văn bản

`expandproperties` thay biểu thức Ant property như `${app.version}` nằm trong nội dung tệp bằng giá trị property hiện tại.

Ví dụ tệp `message.txt`:

```text
Application: ${app.name}
Version: ${app.version}
```

Build file:

```xml
<project name="expand-demo" default="expand-message">
    <property name="app.name" value="inventory"/>
    <property name="app.version" value="2.4.0"/>

    <target name="expand-message">
        <copy file="message.txt" tofile="build/message.txt">
            <filterchain>
                <expandproperties/>
            </filterchain>
        </copy>
    </target>
</project>
```

Nội dung đầu ra:

```text
Application: inventory
Version: 2.4.0
```

Từ Ant 1.8.3, `expandproperties` có thể nhận một nested `<propertyset>` để giới hạn property được phép mở rộng. Điều này hữu ích khi chỉ muốn thay một nhóm property cụ thể trong nội dung.

Không nhầm `expandproperties` với `replacetokens`. `expandproperties` tìm cú pháp `${...}` của Ant; `replacetokens` tìm token có dấu phân cách do người dùng quy định, mặc định là `@...@`.

## 7. Chuẩn hóa dòng và khoảng trắng

### 7.1. `prefixlines` và `suffixlines`

`prefixlines` thêm một chuỗi vào đầu mỗi dòng:

```xml
<filterchain>
    <prefixlines prefix="// Generated: "/>
</filterchain>
```

`suffixlines` thêm chuỗi vào cuối mỗi dòng (có từ Ant 1.8.0):

```xml
<filterchain>
    <suffixlines suffix=" ;"/>
</filterchain>
```

Các filter này hữu ích khi tạo tệp văn bản có đánh dấu nguồn sinh, định dạng dòng hoặc thêm cú pháp bao quanh mỗi dòng. Hãy bảo đảm chuỗi được thêm phù hợp với định dạng đầu ra; ví dụ thêm `//` chỉ phù hợp với định dạng có cú pháp comment kiểu đó.

### 7.2. `tabstospaces`

Filter `tabstospaces` thay ký tự tab bằng dấu cách. Thuộc tính `tablength` đặt số dấu cách thay cho một tab; mặc định là 8:

```xml
<filterchain>
    <tabstospaces tablength="4"/>
</filterchain>
```

Filter này có thể chuẩn hóa thụt lề trong các tệp văn bản. Tuy nhiên, nó không hiểu cú pháp của ngôn ngữ lập trình và không đảm bảo định dạng mã nguồn theo một style guide hoàn chỉnh.

### 7.3. `striplinebreaks`

`striplinebreaks` xóa các ký tự xuống dòng. Mặc định filter xóa `\r` và `\n`:

```xml
<filterchain>
    <striplinebreaks/>
</filterchain>
```

Có thể chỉ định tập ký tự cần xóa qua thuộc tính `linebreaks` khi dùng dạng filter reader tổng quát. Ví dụ xóa dấu ngoặc tròn:

```xml
<filterreader classname="org.apache.tools.ant.filters.StripLineBreaks">
    <param name="linebreaks" value="()"/>
</filterreader>
```

Hãy cẩn thận: xóa ký tự xuống dòng sẽ nối nội dung các dòng lại với nhau. Điều này có thể phá cấu trúc của tệp properties, CSV, Java hoặc các định dạng mà ranh giới dòng mang ý nghĩa.

### 7.4. `striplinecomments` và `stripjavacomments`

`striplinecomments` bỏ những dòng bắt đầu bằng chuỗi comment đã khai báo:

```xml
<filterchain>
    <striplinecomments>
        <comment value="#"/>
        <comment value="//"/>
    </striplinecomments>
</filterchain>
```

Filter này phù hợp với định dạng cấu hình đơn giản có dòng comment bắt đầu bằng `#` hoặc `//`. Nó không tự loại comment nằm giữa một dòng và không phân tích cú pháp ngôn ngữ.

`stripjavacomments` loại bỏ comment theo cú pháp Java:

```xml
<filterchain>
    <stripjavacomments/>
</filterchain>
```

Chỉ dùng filter này cho dữ liệu Java phù hợp. Không dùng nó để xử lý tùy tiện tệp XML, properties, JavaScript hoặc các ngôn ngữ có quy tắc comment khác.

## 8. Chọn một phần nội dung bằng HeadFilter và TailFilter

`headfilter` lấy một số dòng từ đầu luồng. Mặc định lấy 10 dòng; thuộc tính `lines` thay đổi số dòng cần giữ. Thuộc tính `skip` bỏ qua một số dòng đầu tiên trước khi lấy dữ liệu.

Ví dụ lấy dòng 3 đến dòng 17:

```xml
<filterchain>
    <headfilter lines="15" skip="2"/>
</filterchain>
```

`tailfilter` lấy một số dòng từ cuối luồng và có thể bỏ qua một số dòng cuối:

```xml
<filterchain>
    <tailfilter lines="10" skip="2"/>
</filterchain>
```

Ví dụ này lấy 10 dòng cuối sau khi bỏ qua hai dòng cuối của dữ liệu.

Có thể kết hợp hai filter để lấy một đoạn ở giữa. Ví dụ lấy năm dòng cuối trong 15 dòng đầu:

```xml
<filterchain>
    <headfilter lines="15"/>
    <tailfilter lines="5"/>
</filterchain>
```

Giá trị `lines="-1"` có nghĩa là chuyển tiếp toàn bộ số dòng còn lại, thường hữu ích khi chỉ muốn bỏ qua một số dòng bằng `skip`.

## 9. Xử lý token bằng TokenFilter

`tokenfilter` chia luồng đầu vào thành token rồi áp dụng các bộ lọc chuỗi lên từng token. Mặc định, `LineTokenizer` tách dữ liệu theo dòng. Có thể chọn tokenizer khác nếu muốn xử lý toàn bộ nội dung hoặc tách theo khoảng trắng.

Ví dụ loại bỏ dòng trống, xóa tab và cắt khoảng trắng ở đầu/cuối mỗi dòng:

```xml
<filterchain>
    <tokenfilter>
        <deletecharacters chars="\t"/>
        <trim/>
        <ignoreblank/>
    </tokenfilter>
</filterchain>
```

Các bộ lọc trong `tokenfilter` được áp dụng lần lượt cho từng token:

- `deletecharacters` xóa những ký tự được chỉ định.
- `trim` xóa khoảng trắng ở đầu và cuối token.
- `ignoreblank` loại bỏ token rỗng.
- `replacestring` thay chuỗi cố định.
- `replaceregex` thay chuỗi theo biểu thức chính quy.
- `containsstring` hoặc `containsregex` chỉ giữ token khớp điều kiện.
- `uniqfilter` loại bỏ token trùng với token trước đó; thường hữu ích sau khi sắp xếp.

### 9.1. Thay chuỗi bằng `replacestring`

Ví dụ thay `localhost` bằng `staging.example.com` trong từng dòng:

```xml
<filterchain>
    <tokenfilter>
        <replacestring from="localhost" to="staging.example.com"/>
    </tokenfilter>
</filterchain>
```

### 9.2. Thay bằng biểu thức chính quy

`replaceregex` thay các phần khớp với mẫu regex. Ví dụ đổi chuỗi `version=1.0` thành `version=2.0`:

```xml
<filterchain>
    <tokenfilter>
        <replaceregex pattern="version=[0-9.]+"
                      replace="version=2.0"/>
    </tokenfilter>
</filterchain>
```

Có thể dùng cờ regex như `i` để bỏ qua phân biệt chữ hoa/thường và `g` để thay mọi lần khớp theo hành vi của filter. Cú pháp regex và cờ được mô tả trong tài liệu Regexp/ReplaceRegexp của Ant.

### 9.3. Chọn tokenizer phù hợp

`tokenfilter` hỗ trợ một tokenizer. Nếu không khai báo, `LineTokenizer` là mặc định:

| Tokenizer | Cách chia dữ liệu | Khi nào dùng |
|---|---|---|
| `linetokenizer` | Chia theo dòng, nhận `\r`, `\n` hoặc `\r\n` | Lọc log, dòng cấu hình hoặc danh sách văn bản |
| `filetokenizer` | Coi toàn bộ đầu vào là một token | Biến đổi mẫu văn bản trên toàn tệp; tránh với tệp rất lớn |
| `stringtokenizer` | Chia theo khoảng trắng hoặc tập ký tự phân cách | Xử lý danh sách token hoặc từ |

Ví dụ bao mỗi token không phải khoảng trắng bằng dấu ngoặc vuông:

```xml
<filterchain>
    <tokenfilter>
        <stringtokenizer/>
        <replaceregex pattern="(.+)" replace="[\1]"/>
    </tokenfilter>
</filterchain>
```

`filetokenizer` coi toàn bộ dữ liệu là một token nên có thể cần giữ nhiều nội dung trong bộ nhớ. Không nên chọn nó cho tệp rất lớn nếu không thật sự cần xử lý toàn bộ nội dung như một chuỗi duy nhất.

## 10. Thứ tự filter ảnh hưởng kết quả

FilterChain xử lý filter theo thứ tự khai báo. Hai chuỗi có cùng filter nhưng thứ tự khác nhau có thể cho kết quả khác nhau.

Ví dụ chuỗi A:

```xml
<filterchain>
    <headfilter lines="20"/>
    <linecontains>
        <contains value="ERROR"/>
    </linecontains>
</filterchain>
```

Chuỗi này chỉ tìm `ERROR` trong 20 dòng đầu tiên.

Chuỗi B:

```xml
<filterchain>
    <linecontains>
        <contains value="ERROR"/>
    </linecontains>
    <headfilter lines="20"/>
</filterchain>
```

Chuỗi này trước tiên giữ tất cả dòng có `ERROR`, sau đó chỉ lấy 20 dòng đầu tiên trong kết quả đã lọc. Hai chuỗi không tương đương nếu số dòng lỗi vượt quá hoặc nằm rải rác trong tệp.

Khi thiết kế chuỗi, hãy xác định rõ:

1. Dữ liệu cần lọc theo dòng, token hay toàn bộ nội dung?
2. Bước nào phải xảy ra trước để các bước sau nhận đúng dữ liệu?
3. Có filter nào xóa dòng, thay đổi ranh giới dòng hoặc làm thay đổi nội dung mà điều kiện tiếp theo cần đọc không?
4. Kết quả cuối có còn đúng định dạng mà task đích mong đợi không?

## 11. Tái sử dụng FilterChain bằng `refid`

Nếu nhiều task cần cùng một chuỗi xử lý, có thể khai báo FilterChain một lần rồi tham chiếu bằng `refid`:

```xml
<project name="shared-filterchain" default="copy-text">

    <filterchain id="normalize-text">
        <tokenfilter>
            <trim/>
            <ignoreblank/>
        </tokenfilter>
        <prefixlines prefix="[NORMALIZED] "/>
    </filterchain>

    <target name="copy-text">
        <copy file="input.txt" tofile="build/input.txt">
            <filterchain refid="normalize-text"/>
        </copy>
    </target>

</project>
```

Khi FilterChain dùng `refid`, nó tham chiếu một FilterChain đã được khai báo. Không đặt thêm filter hoặc thuộc tính khác trong phần tử chỉ dùng để tham chiếu. Cách tái sử dụng này giúp các task áp dụng cùng một quy tắc xử lý và giảm việc sao chép cấu hình.

## 12. Viết FilterReader tùy chỉnh

Nếu các filter có sẵn không đáp ứng yêu cầu, có thể viết FilterReader riêng bằng Java. Một FilterReader tùy chỉnh cần kế thừa `java.io.FilterReader` và có thể được khai báo trong build file bằng `<filterreader classname="..."/>`.

Ví dụ cấu trúc khai báo:

```xml
<copy file="input.txt" tofile="build/output.txt">
    <filterchain>
        <filterreader classname="com.example.ant.UppercaseFilter">
            <classpath>
                <pathelement location="lib/custom-filters.jar"/>
            </classpath>
            <param name="locale" value="vi-VN"/>
        </filterreader>
    </filterchain>
</copy>
```

Tên class, JAR và tham số trong ví dụ là minh họa. Class được chỉ định phải có sẵn trên classpath của filter; nếu cần nhận tham số cấu hình, implementation phải hỗ trợ cơ chế `Parameterizable` mà Ant yêu cầu cho FilterReader.

Với nhu cầu lọc token thay vì xử lý Reader trực tiếp, Ant còn cho phép tạo bộ lọc tùy chỉnh bằng cách triển khai `TokenFilter.Filter` và đăng ký qua `<typedef>`. Cách này phù hợp khi phép biến đổi làm việc trên từng chuỗi token.

## 13. Lưu ý về văn bản, encoding và dữ liệu nhị phân

FilterChain hoạt động trên luồng ký tự. Hãy dùng nó cho tệp văn bản như `.txt`, `.properties`, `.xml`, `.csv`, log hoặc template. Không áp dụng các filter văn bản cho JAR, hình ảnh, tệp nén hoặc dữ liệu nhị phân khác vì việc chuyển byte sang ký tự rồi biến đổi có thể làm hỏng nội dung.

Khi xử lý văn bản có ký tự ngoài ASCII, hãy quan tâm đến encoding của task đọc và ghi. Nếu nguồn và đích dùng encoding khác nhau, cấu hình encoding phù hợp theo thuộc tính của task đang dùng. Đừng giả định rằng FilterChain tự nhận biết chính xác mọi encoding.

Một số filter thay đổi số dòng, khoảng trắng hoặc token. Chúng có thể làm mất định dạng ban đầu. Ví dụ, `striplinebreaks` nối các dòng lại với nhau, `trim` loại bỏ khoảng trắng ở đầu/cuối token và `sortfilter` sắp xếp lại thứ tự dòng. Chỉ dùng khi định dạng đầu ra cho phép các thay đổi đó.

Với nội dung có secret, token truy cập hoặc dữ liệu cá nhân, tránh ghi giá trị đã mở rộng vào log hoặc tệp đầu ra có quyền truy cập rộng. Đặc biệt, `expandproperties` có thể chèn giá trị property vào nội dung, vì vậy hãy chỉ mở rộng những property cần thiết.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ant báo nested `filterchain` không hợp lệ | Task đang dùng không hỗ trợ FilterChain hoặc đặt sai vị trí | Kiểm tra tài liệu task và đặt FilterChain ở đúng cấp lồng |
| Token không được thay thế | Token trong tệp không khớp key hoặc dấu mở/đóng | Đối chiếu token chính xác, `begintoken`, `endtoken` và key đã khai báo |
| `${property}` vẫn còn nguyên trong đầu ra | Chưa dùng `expandproperties` hoặc property chưa được khai báo | Thêm filter phù hợp và bảo đảm property có giá trị trước khi lọc |
| Không còn dòng nào sau khi lọc | Điều kiện `linecontains` hoặc regex quá chặt | Kiểm tra dữ liệu nguồn, mẫu và quy tắc `matchAny`/`negate` |
| Kết quả khác khi đổi thứ tự filter | Mỗi filter nhận dữ liệu đã biến đổi từ filter trước | Sắp xếp lại chuỗi theo trình tự xử lý mong muốn |
| Tệp đầu ra bị mất xuống dòng | Dùng `striplinebreaks` hoặc tokenizer/delimiter không phù hợp | Bỏ filter xóa dòng hoặc đặt delimiter đầu ra thích hợp |
| Tệp đầu ra bị hỏng | Dùng FilterChain trên dữ liệu nhị phân hoặc encoding không phù hợp | Chỉ lọc văn bản và cấu hình encoding đúng cho task |
| FilterReader tùy chỉnh không được tìm thấy | Class hoặc dependency không có trong classpath của filter | Khai báo nested `<classpath>` hoặc đường dẫn thư viện phù hợp |
| Xử lý tệp lớn chậm hoặc tốn bộ nhớ | Dùng filter cần đọc toàn bộ nội dung, ví dụ `filetokenizer` hoặc `sortfilter` | Chọn filter theo dòng khi có thể và tránh giữ toàn bộ tệp trong bộ nhớ |

## 15. Ví dụ tổng hợp: lọc log và tạo cấu hình

Ví dụ sau thực hiện hai công việc khác nhau bằng FilterChain: trích dòng lỗi từ log và tạo tệp cấu hình từ template.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="filterchain-example" default="prepare-output" basedir=".">

    <property name="app.name" value="inventory"/>
    <property name="app.version" value="2.4.0"/>
    <property name="app.environment" value="staging"/>

    <target name="filter-log">
        <copy file="logs/application.log"
              tofile="build/application-errors.log">
            <filterchain>
                <linecontains matchAny="true">
                    <contains value="ERROR"/>
                    <contains value="FATAL"/>
                </linecontains>
                <prefixlines prefix="[REVIEW] "/>
            </filterchain>
        </copy>
    </target>

    <target name="prepare-config">
        <copy file="config/app.properties.template"
              tofile="build/app.properties">
            <filterchain>
                <replacetokens>
                    <token key="APP_NAME" value="${app.name}"/>
                    <token key="APP_VERSION" value="${app.version}"/>
                    <token key="ENVIRONMENT" value="${app.environment}"/>
                </replacetokens>
            </filterchain>
        </copy>
    </target>

    <target name="prepare-output" depends="filter-log,prepare-config">
        <echo message="Filtered log and application configuration are ready."/>
    </target>

</project>
```

Tệp mẫu `config/app.properties.template`:

```properties
app.name=@APP_NAME@
app.version=@APP_VERSION@
app.environment=@ENVIRONMENT@
```

Khi chạy `ant prepare-output`, Ant thực hiện hai target phụ thuộc. `filter-log` chỉ giữ dòng chứa `ERROR` hoặc `FATAL`, sau đó thêm tiền tố `[REVIEW] `. `prepare-config` thay ba token trong tệp mẫu bằng property của build. Cả hai task ghi kết quả vào thư mục `build`.

Ví dụ giả định thư mục nguồn và tệp đầu vào đã tồn tại. Nếu cần tạo thư mục `build` trước, hãy thêm task `<mkdir dir="build"/>` vào target chuẩn bị hoặc tạo dependency `prepare-directories` cho cả hai target xử lý.

## 16. Checklist sử dụng FilterChain

- [ ] Task đang dùng hỗ trợ nested `<filterchain>`.
- [ ] FilterChain chỉ xử lý dữ liệu văn bản có encoding phù hợp.
- [ ] Các filter được sắp xếp đúng thứ tự biến đổi mong muốn.
- [ ] Mẫu lọc dòng và regex đã được chọn theo dữ liệu thực tế.
- [ ] Token thay thế khớp chính xác dấu mở, dấu đóng và key.
- [ ] Property cần mở rộng đã được khai báo trước khi FilterChain chạy.
- [ ] Đã cân nhắc tác động của việc xóa dòng, khoảng trắng hoặc ký tự xuống dòng.
- [ ] Đầu ra được ghi vào vị trí phù hợp và không ghi đè nhầm tệp nguồn.
- [ ] FilterChain dùng chung được tái sử dụng bằng `refid` khi phù hợp.
- [ ] Không in hoặc mở rộng secret vào log hay đầu ra không được bảo vệ.

FilterChain biến các thao tác xử lý văn bản thành những bước có thể kết hợp và tái sử dụng trong build file Ant. Khi chọn đúng task, đúng filter và đúng thứ tự, bạn có thể lọc log, tạo cấu hình từ template, chuẩn hóa nội dung và chuẩn bị tài nguyên cho các giai đoạn build tiếp theo mà vẫn giữ quy trình được mô tả rõ trong `build.xml`.

Tài liệu tham khảo: [Apache Ant Manual — FilterChains and FilterReaders](https://ant.apache.org/manual/Types/filterchain.html).
