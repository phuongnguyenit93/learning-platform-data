# ResourceBundle: Định dạng bundle và danh sách locale ứng viên

## Mục tiêu

**java.util.ResourceBundle** giúp ứng dụng Java lấy văn bản và các tài nguyên bản địa hóa theo một **Locale** cụ thể. Khi gọi **ResourceBundle.getBundle(...)**, Java không chỉ tìm một file tên giống locale: nó xác định những **candidate locales**, thử các **bundle formats**, chọn một bundle có sẵn và xây dựng **parent chain** để tra cứu những key còn thiếu.

Sau bài này, bạn có thể:

1. Phân biệt **base bundle name**, **requested Locale**, **candidate Locale**, **actual loaded Locale**, **format**, **fallback Locale** và **parent-key lookup**.
2. Giải thích định dạng mặc định **java.class** và **java.properties**, thứ tự ưu tiên và khi nào dùng **ResourceBundle.Control.FORMAT_DEFAULT**, **FORMAT_PROPERTIES**, **FORMAT_CLASS**.
3. Hiểu quy tắc tên **Messages_vi_VN.properties** từ language tag **vi-VN**, cùng bundle gốc **Messages.properties**.
4. Dùng **ResourceBundle.Control.getCandidateLocales(...)** để lấy thứ tự ứng viên cho **vi-VN** và locale có script **zh-Hant-TW**, thay vì tự ghép suffix tùy ý.
5. Phân biệt fallback khi **thiếu bundle**, fallback theo **Locale.getDefault()** và lookup qua **parent bundle** khi thiếu key.
6. Hiểu tại sao **getNoFallbackControl(...)** chặn thử default locale nhưng **không loại root và parent bundles**.
7. Làm việc với tệp **.properties UTF-8** chứa tiếng Việt trên JDK hiện đại, cùng cách đóng gói resources vào classpath.
8. Biên dịch và chạy ví dụ Java 17+ kiểm chứng candidate lists, formats, root/parent fallback, MissingResourceException và ưu tiên class trước properties.
9. Nhận biết cache, named modules, encoding, packaging, key coverage và các lỗi chọn nhầm bundle.

**Giới hạn kiến thức:** Ví dụ dựa trên API được hỗ trợ hiện nay trong **java.base**, dùng **JDK 17+**; đã chạy thành công với **OpenJDK 24.0.2** và **--release 17**. Không dùng quy tắc nguồn lực hoặc encoding cũ như yêu cầu bắt buộc của Java mới.

## 1. ResourceBundle chọn resource như thế nào?

Một ứng dụng dùng base name **demo.i18n.Messages**, và có các files:

~~~text
demo/i18n/
├── Messages.properties
├── Messages_vi.properties
└── Messages_vi_VN.properties
~~~

Nếu người dùng chọn tiếng Việt tại Việt Nam:

~~~java
// Mảnh minh họa, cần import java.util.Locale và ResourceBundle.
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle messages =
        ResourceBundle.getBundle("demo.i18n.Messages", locale);
~~~

ResourceBundle phải giải quyết các vấn đề khác nhau:

~~~text
getBundle("demo.i18n.Messages", vi-VN)
                  │
                  ▼
       Candidate locales
            vi-VN → vi → root
                  │
                  ▼
        Formats cho mỗi candidate
          java.class → java.properties
                  │
                  ▼
        Chọn bundle tìm được phù hợp
                  │
                  ▼
      Gắn các parent bundles có sẵn
                  │
                  ▼
         getString("some.key")
          ├── trong bundle cụ thể
          ├── nếu thiếu, trong parent
          └── nếu không có, MissingResourceException
~~~

**Một candidate locale không bảo đảm bundle tương ứng tồn tại**. **bundle.getLocale()** phản ánh locale thực tế của bundle được tải, không nhất thiết locale đã yêu cầu.

## 2. Tên resource và các thành phần Locale

### 2.1. Base name không phải đường dẫn file đầy đủ

Khi file nằm tại **demo/i18n/Messages_vi_VN.properties**, base name là:

~~~text
demo.i18n.Messages
~~~

Không truyền **demo/i18n/Messages**, **demo.i18n.Messages.properties** hoặc hậu tố **_vi_VN** vào base name của một family resource theo convention chuẩn.

Trong build tool, file thường được đặt tại:

~~~text
src/main/resources/demo/i18n/Messages.properties
src/main/resources/demo/i18n/Messages_vi.properties
src/main/resources/demo/i18n/Messages_vi_VN.properties
~~~

Build phải copy các tệp đó đến **demo/i18n/** trong output classes/JAR; chỉ tồn tại ở nguồn là chưa đủ nếu runtime không thấy chúng.

### 2.2. Locale tag và tên file khác cú pháp

**Locale.forLanguageTag("vi-VN")** tạo Locale với **language=vi**, **region=VN**. **Locale.toLanguageTag()** thường in **vi-VN** theo BCP 47. Còn bundle suffix theo convention ResourceBundle có các dấu gạch dưới:

~~~text
BCP 47 language tag : vi-VN
Bundle suffix       : _vi_VN
Bundle resource     : Messages_vi_VN.properties
~~~

Một số Locale còn có **script** như **Hant**, hoặc **variant**. Với locale phức tạp, candidate list không đơn thuần là bỏ dần những phần ngăn bằng dấu gạch nối.

### 2.3. Locale.ROOT có ý nghĩa gì?

**Locale.ROOT** là Locale không có language/script/region/variant. Bundle gốc tương ứng với **Messages.properties**. Đừng coi root đồng nghĩa với tiếng Anh: app tự quyết định root chứa ngôn ngữ mặc định nào.

**Locale.ROOT.toString()** thường là chuỗi rỗng, còn **toLanguageTag()** có thể là **und**. Để logs dễ đọc, ví dụ sẽ hiển thị root bằng chuỗi **<root>**.

Một bundle root là lựa chọn có thể dùng khi không tìm được bản địa hóa phù hợp, đồng thời có thể là **parent của những bundle cụ thể**.

## 3. Hai định dạng chuẩn của ResourceBundle

ResourceBundle mặc định hỗ trợ hai format:

| Format | Đầu vào | Implementation phổ biến |
| --- | --- | --- |
| **java.class** | Class được compile theo tên bundle | **ListResourceBundle** hoặc một subclass ResourceBundle |
| **java.properties** | File text .properties | **PropertyResourceBundle** |

Danh sách có sẵn:

~~~java
ResourceBundle.Control.FORMAT_DEFAULT
ResourceBundle.Control.FORMAT_PROPERTIES
ResourceBundle.Control.FORMAT_CLASS
~~~

Giá trị:

~~~text
FORMAT_DEFAULT    = [java.class, java.properties]
FORMAT_PROPERTIES = [java.properties]
FORMAT_CLASS      = [java.class]
~~~

**Thứ tự trong FORMAT_DEFAULT có ý nghĩa**: cùng một candidate locale, loader thử **class trước properties**. Đây là thứ tự format, không phải thứ tự candidate locale.

Với **vi-VN**, nếu dùng format mặc định, trình tự cặp locale/format điển hình là:

~~~text
1. Messages_vi_VN.class
2. Messages_vi_VN.properties
3. Messages_vi.class
4. Messages_vi.properties
5. Messages.class
6. Messages.properties
~~~

Trình tự minh họa là **thứ tự lookup logic**, có thể được đáp ứng từ cache và không phải một yêu cầu rằng cả sáu artifact tồn tại.

### 3.1. Property-based bundle

Ví dụ **Messages_vi_VN.properties**:

~~~properties
title=Xin chào Việt Nam
button.ok=Đồng ý
button.cancel=Hủy
~~~

Tệp .properties ánh xạ key đến chuỗi. Cách này thích hợp cho thông điệp UI, CLI, nhãn/nút và localization thông thường; translator có thể làm việc với resource text mà không cần sửa Java source.

Những điểm quan trọng:

- Mỗi file phải có đúng tên candidate và nằm đúng package resource path.
- Các key được truy cập bởi **getString("button.ok")**, **containsKey(...)**, **keySet()**, v.v.
- **MissingResourceException** xảy ra nếu key không có ở bundle được chọn và các parents.
- File properties không tự hỗ trợ mọi yêu cầu biến số, pluralization hay sắp xếp từ; khi cần format, dùng API formatter phù hợp như **MessageFormat** với locale đúng.
- Không đưa secrets/password/API tokens vào file localization.
- Đảm bảo build pipeline copy file vào runtime artifact, không chỉ giữ trong thư mục source.

### 3.2. Class-based bundle

**ListResourceBundle** là API chuẩn hiện hành để khai báo key/value qua Java class:

~~~java
// Mảnh file mẫu: demo/i18n/Labels_vi_VN.java
package demo.i18n;

import java.util.ListResourceBundle;

public final class Labels_vi_VN extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"title", "title from class"}
        };
    }
}
~~~

Khi compile, tạo class **demo.i18n.Labels_vi_VN**. Nó có thể được chọn với base name **demo.i18n.Labels** và locale **vi-VN**. **ListResourceBundle** chứa các cặp key/object; value không nhất thiết String, nhưng **getString** yêu cầu value đúng kiểu String.

Class bundle phù hợp với một số tài nguyên có giá trị dạng object hoặc cấu hình Java phù hợp. Tuy nhiên, **một class bundle là Java code**: không nên nạp từ nguồn không tin cậy và không nên đưa tác dụng phụ phức tạp vào việc đọc văn bản dịch.

### 3.3. Nếu có cả class và properties trùng locale?

Giả sử artifact chứa:

~~~text
Labels_vi_VN.class
Labels_vi_VN.properties
~~~

Với **FORMAT_DEFAULT**, class được ưu tiên. Vì vậy sửa text trong .properties mà app vẫn đọc class cũ là một triệu chứng có thể xảy ra. Với **FORMAT_PROPERTIES**, lookup giới hạn ở .properties.

Đừng dùng class và properties trùng cùng family/locale trừ khi bạn biết rõ lý do. Ngoài format precedence, **ResourceBundle cache** cũng có thể làm kết quả bất ngờ khi thay Control giữa các lần gọi.

## 4. UTF-8 trong PropertyResourceBundle hiện đại

Trên **Java 9 trở lên**, **PropertyResourceBundle** dùng **UTF-8 mặc định** khi đọc properties qua InputStream. Vì vậy với JDK 17+, bạn có thể ghi trực tiếp tiếng Việt bằng UTF-8:

~~~properties
greeting=Xin chào
country=Việt Nam
prompt=Bạn muốn tiếp tục?
~~~

Đây là kiến thức quan trọng khi đọc tài liệu cũ: không còn yêu cầu bắt buộc phải chuyển tất cả ký tự tiếng Việt thành **\\uXXXX** hoặc lưu file theo ISO-8859-1 như trong một số quy trình đã lỗi thời.

**Chi tiết contract cần nắm:**

- Nếu input stream chứa bytes không giải mã được bằng UTF-8, PropertyResourceBundle có cơ chế thử lại bằng ISO-8859-1 để hỗ trợ dữ liệu cũ, trừ khi encoding được buộc rõ qua system property liên quan.
- System property **java.util.PropertyResourceBundle.encoding** có thể đặt **UTF-8** hoặc **ISO-8859-1** theo tài liệu. Nếu cần buộc UTF-8, cấu hình ở lúc khởi tạo JVM/class phù hợp, không đợi sau khi đã dùng PropertyResourceBundle.
- **Properties.load(InputStream)** là một API khác, với quy tắc charset riêng. Đừng suy luận rằng mọi lần đọc .properties qua mọi Java API đều dùng UTF-8 như PropertyResourceBundle.
- **-encoding UTF-8** của javac chỉ cấu hình cách đọc Java source. Nó **không tự chuyển đổi encoding** của .properties files được copy vào output.
- File properties còn có cú pháp escape/backslash, comment và ký tự phân tách key/value; kiểm tra khi dữ liệu có dấu **=**, **:**, backslash, khoảng trắng đầu dòng hoặc newline.
- Nên giữ source properties bằng UTF-8 không có BOM nếu build pipeline cho phép, kiểm tra kết quả bằng phép đọc thực tế từ artifact.

**Trọng tâm vận hành:** dùng UTF-8 từ editor → repository → build → JAR/classes → runtime, có test chứa các chữ tiếng Việt thật. Cơ chế fallback encoding không nên trở thành cách che lỗi lưu file.

## 5. Candidate locales: thứ tự Java tìm bundle

API quan trọng:

~~~java
// Mảnh minh họa, có import ResourceBundle và Locale.
ResourceBundle.Control control =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

List<Locale> candidates = control.getCandidateLocales(
        "demo.i18n.Messages", Locale.forLanguageTag("vi-VN"));
~~~

**getCandidateLocales** tính ra danh sách thứ tự Locale cần thử. Nó không kiểm tra tệp nào có thật. Kết quả đơn giản và phổ biến:

~~~text
vi-VN -> vi -> <root>
~~~

Cũng chính là các suffix:

~~~text
Messages_vi_VN
Messages_vi
Messages
~~~

### 5.1. Locale có script: zh-Hant-TW

Với **Locale.forLanguageTag("zh-Hant-TW")**, kết quả được quan sát trong chương trình test là:

~~~text
zh-Hant-TW -> zh-Hant -> zh-TW -> zh -> <root>
~~~

Ví dụ này giúp thấy **script** và **region** có các bước giảm mức cụ thể khác nhau. Các resource candidates tương ứng gồm:

~~~text
Messages_zh_Hant_TW.properties
Messages_zh_Hant.properties
Messages_zh_TW.properties
Messages_zh.properties
Messages.properties
~~~

**Không tự cắt language tag** rồi cho rằng đã tái hiện đủ thuật toán của JDK. Candidate generation có những special cases và biến thể với language, script, country, variant; cách đúng để kiểm tra là dùng chính API với những Locale bạn phải hỗ trợ.

### 5.2. Candidate list không phải danh sách resources đã tìm thấy

Một Locale xuất hiện trong danh sách **không có nghĩa** file tương ứng có mặt. Khi thiếu **Messages_vi_VN.properties**, loader có thể tìm tiếp ở **Messages_vi.properties**. Nếu không có cả vi, root hoặc fallback locale có thể được xét theo Control.

Nếu muốn biết bundle được chọn cuối cùng, dùng:

~~~java
// Mảnh minh họa sau khi getBundle đã trả về.
Locale actual = bundle.getLocale();
~~~

Không dùng **requestedLocale** như bằng chứng rằng app đã tìm được bundle tại locale đó.

### 5.3. Đừng cứng hóa số candidates

Một locale có variant phức tạp hoặc script có thể tạo nhiều bước ứng viên hơn ba. Một số locale có những ngoại lệ chuẩn được JDK tài liệu hóa, nên unit test nên gọi **getCandidateLocales** thay vì tự định nghĩa thứ tự sai.

Khi tự viết **ResourceBundle.Control** tùy chỉnh, bạn có thể thay danh sách candidate theo policy, nhưng phải bảo đảm thứ tự hợp lệ, consistency và không gây fallback bất ngờ.

## 6. Ba cơ chế fallback phải tách biệt

Nhiều lỗi quốc tế hóa xuất phát từ việc dùng từ “fallback” cho ba hành vi khác nhau.

### 6.1. Fallback sang locale ít cụ thể hơn

Khi requested locale **vi-VN** không có bundle riêng, các candidate tiếp theo gồm **vi** và **root**. Nếu có **Messages_vi.properties**, đó có thể là bundle được chọn thực tế, với **bundle.getLocale()** là **vi**.

Đây là bước **candidate selection**.

### 6.2. Fallback sang JVM default locale

**Locale.getDefault()** là locale mặc định của JVM. Khi không tìm được bundle phù hợp với requested locale, ResourceBundle với Control mặc định có thể thử **default locale**.

**Chi tiết quan trọng:** Nếu quá trình tìm target chỉ gặp **root bundle**, ResourceBundle có thể tạm giữ root và tìm tiếp theo default locale; không nên khẳng định root luôn được trả lập tức trước mọi khả năng fallback. Nếu không có fallback thích hợp, root mới có thể được dùng như lựa chọn sau cùng.

Điều này giải thích vì sao trên một máy dùng mặc định **en-US**, yêu cầu **fr-CA** nhưng thiếu resource tiếng Pháp có thể trả về bundle tiếng Anh thay vì root, tùy tập file và Control.

### 6.3. Parent-key lookup sau khi chọn bundle

Khi bundle **vi-VN** được chọn nhưng thiếu key **sharedVi**, Java có thể tra trong parent **vi**, rồi root. **Parent lookup không đổi bundle.getLocale()**: selected bundle vẫn là vi-VN dù một key được tìm ở file ít cụ thể hơn.

Ví dụ:

~~~text
Messages_vi_VN.properties
    title=Xin chào Việt Nam

Messages_vi.properties
    title=Xin chào
    sharedVi=from vi

Messages.properties
    title=Root title
    sharedRoot=from root
~~~

Khi selected bundle là vi-VN:

| Key | Nguồn | Giá trị |
| --- | --- | --- |
| title | vi-VN | Xin chào Việt Nam |
| sharedVi | vi | from vi |
| sharedRoot | root | from root |

**Một bundle được chọn ở locale cụ thể không có nghĩa tất cả key đều đã được dịch tại locale đó.**

## 7. getControl và getNoFallbackControl

Các factory hiện hành:

~~~java
ResourceBundle.Control standard =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_DEFAULT);

ResourceBundle.Control propertiesOnly =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle.Control propertiesWithoutDefaultFallback =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);
~~~

Trong đó:

- **getControl(FORMAT_DEFAULT)** giữ hai formats **class rồi properties** và default-fallback policy của Control.
- **getControl(FORMAT_PROPERTIES)** chỉ tìm properties nhưng vẫn có cơ chế fallback locale mặc định.
- **getNoFallbackControl(FORMAT_PROPERTIES)** chỉ tìm properties và **getFallbackLocale** trả null, không thử **Locale.getDefault()**.

**No fallback ở đây không có nghĩa bỏ root**. **Locale.ROOT** vẫn ở candidate list chuẩn và bundle gốc vẫn có thể được chọn. Đồng thời, parent-key lookup vẫn hoạt động đối với bundle đã được chọn.

Nếu cả candidate/root đều không có bundle, **ResourceBundle.getBundle(...)** có thể ném **MissingResourceException**. Nếu bundle tồn tại nhưng key vắng mặt trên cả parent chain, **getString** cũng có thể ném cùng ngoại lệ.

## 8. Chương trình chạy được Java 17+: candidate + format + keys

Ví dụ dưới đây có **một Java source** và **ba file UTF-8 .properties**. Nó được kiểm thử trên OpenJDK 24.0.2 với **--release 17**, bao gồm output tiếng Việt, candidate orders và missing-key behavior.

### 8.1. Cấu trúc ban đầu

~~~text
bundle-demo/
├── src/demo/i18n/BundleFormatsDemo.java
└── resources/demo/i18n/
    ├── Messages.properties
    ├── Messages_vi.properties
    └── Messages_vi_VN.properties
~~~

### 8.2. Các properties files

**resources/demo/i18n/Messages.properties**

~~~properties
title=Root title
sharedRoot=from root
~~~

**resources/demo/i18n/Messages_vi.properties**

~~~properties
title=Xin chào
sharedVi=from vi
~~~

**resources/demo/i18n/Messages_vi_VN.properties**

~~~properties
title=Xin chào Việt Nam
~~~

Không phải copy key **sharedVi** hay **sharedRoot** vào vi-VN: ví dụ cố ý để chứng minh lookup qua parent bundle.

### 8.3. Source Java hoàn chỉnh

**src/demo/i18n/BundleFormatsDemo.java**

~~~java
package demo.i18n;

import java.util.List;
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;
import java.util.stream.Collectors;

public final class BundleFormatsDemo {
    private static final String BASE = "demo.i18n.Messages";
    private static final ResourceBundle.Control PROPERTIES_ONLY =
            ResourceBundle.Control.getNoFallbackControl(
                    ResourceBundle.Control.FORMAT_PROPERTIES);

    private static String label(Locale locale) {
        return Locale.ROOT.equals(locale)
                ? "<root>" : locale.toLanguageTag();
    }

    private static String candidates(Locale locale) {
        List<Locale> locales = PROPERTIES_ONLY.getCandidateLocales(BASE, locale);
        return locales.stream().map(BundleFormatsDemo::label)
                .collect(Collectors.joining(" -> "));
    }

    public static void main(String[] args) {
        Locale viVN = Locale.forLanguageTag("vi-VN");
        System.out.println("formatsDefault="
                + ResourceBundle.Control.FORMAT_DEFAULT);
        System.out.println("formatsProperties="
                + PROPERTIES_ONLY.getFormats(BASE));
        System.out.println("candidatesVi=" + candidates(viVN));
        System.out.println("candidatesZh="
                + candidates(Locale.forLanguageTag("zh-Hant-TW")));

        ResourceBundle vietnamese = ResourceBundle.getBundle(
                BASE, viVN, BundleFormatsDemo.class.getClassLoader(),
                PROPERTIES_ONLY);
        System.out.println("selected=" + label(vietnamese.getLocale()));
        System.out.println("title=" + vietnamese.getString("title"));
        System.out.println("sharedVi=" + vietnamese.getString("sharedVi"));
        System.out.println("sharedRoot=" + vietnamese.getString("sharedRoot"));

        ResourceBundle frenchCanada = ResourceBundle.getBundle(
                BASE, Locale.forLanguageTag("fr-CA"),
                BundleFormatsDemo.class.getClassLoader(), PROPERTIES_ONLY);
        System.out.println("frSelected=" + label(frenchCanada.getLocale()));
        System.out.println("frTitle=" + frenchCanada.getString("title"));
        System.out.println("defaultLocaleFallbackDisabled="
                + (PROPERTIES_ONLY.getFallbackLocale(BASE, viVN) == null));

        try {
            vietnamese.getString("notFound");
        } catch (MissingResourceException expected) {
            System.out.println("missingKey=MissingResourceException");
        }
    }
}
~~~

### 8.4. Lệnh build và run

Với Linux/macOS/Bash, chạy ở thư mục **bundle-demo**:

~~~bash
mkdir -p build/demo/i18n

javac -encoding UTF-8 --release 17 \
    -d build \
    src/demo/i18n/BundleFormatsDemo.java

cp resources/demo/i18n/Messages*.properties build/demo/i18n/

java -cp build demo.i18n.BundleFormatsDemo
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/demo/i18n | Out-Null
javac -encoding UTF-8 --release 17 -d build src/demo/i18n/BundleFormatsDemo.java
Copy-Item resources/demo/i18n/Messages*.properties build/demo/i18n/
java -cp build demo.i18n.BundleFormatsDemo
~~~

**Vì sao cần bước copy?** javac biên dịch Java sources thành classfiles; trong ví dụ lệnh CLI thủ công không tự copy **resources/** vào output classes. Khi dùng Maven/Gradle, resource-processing step thường giải quyết việc này nhưng vẫn phải xác minh JAR thực tế.

### 8.5. Stdout chính xác (đã kiểm chứng)

~~~text
formatsDefault=[java.class, java.properties]
formatsProperties=[java.properties]
candidatesVi=vi-VN -> vi -> <root>
candidatesZh=zh-Hant-TW -> zh-Hant -> zh-TW -> zh -> <root>
selected=vi-VN
title=Xin chào Việt Nam
sharedVi=from vi
sharedRoot=from root
frSelected=<root>
frTitle=Root title
defaultLocaleFallbackDisabled=true
missingKey=MissingResourceException
~~~

**Đây là 12 dòng stdout**, không có dependency ngoài JDK.

Diễn giải:

1. Default format list có class trước properties.
2. Control của chương trình chỉ cho phép properties.
3. vi-VN candidates giảm từ vùng cụ thể xuống language và root.
4. Locale có script như zh-Hant-TW có candidate order phức tạp hơn.
5. Java tìm được bundle vi-VN nên selected Locale là vi-VN.
6. Key title lấy từ resource vi-VN.
7. Key sharedVi và sharedRoot lấy qua parent chain.
8. Với fr-CA và Control không thử default JVM locale, resource root được chọn.
9. Key notFound không tồn tại trong selected bundle/parents, nên getString ném MissingResourceException và code bắt đúng ngoại lệ.

**Điểm QA:** Test dùng chữ **Xin chào Việt Nam** literal UTF-8 trong properties, chứng minh không phải viết Unicode escapes trên Java 17+ khi tệp được tạo đúng encoding.

## 9. Chương trình kiểm chứng class ưu tiên properties

Đây là bài test **độc lập** với base name **demo.i18n.Labels**. Giữ nguyên các file ở bài trước hoặc tạo project mới với package **demo.i18n**; chương trình chỉ phụ thuộc hai file Java và một properties.

### 9.1. Class bundle

**src/demo/i18n/Labels_vi_VN.java**

~~~java
package demo.i18n;

import java.util.ListResourceBundle;

public final class Labels_vi_VN extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"title", "title from class"}
        };
    }
}
~~~

### 9.2. Properties bundle cùng locale

**resources/demo/i18n/Labels_vi_VN.properties**

~~~properties
title=title from properties
~~~

### 9.3. Code test format precedence

**src/demo/i18n/FormatPrecedenceDemo.java**

~~~java
package demo.i18n;

import java.util.Locale;
import java.util.ResourceBundle;

public final class FormatPrecedenceDemo {
    public static void main(String[] args) {
        String base = "demo.i18n.Labels";
        Locale locale = Locale.forLanguageTag("vi-VN");
        ClassLoader loader = FormatPrecedenceDemo.class.getClassLoader();

        System.out.println("defaultFormat="
            + ResourceBundle.getBundle(base, locale, loader).getString("title"));

        ResourceBundle.clearCache(loader);
        ResourceBundle.Control onlyProperties =
            ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);
        System.out.println("propertyOnly="
            + ResourceBundle.getBundle(base, locale, loader, onlyProperties)
                .getString("title"));
    }
}
~~~

### 9.4. Build và output

~~~bash
mkdir -p build/demo/i18n
javac -encoding UTF-8 --release 17 -d build \
    src/demo/i18n/Labels_vi_VN.java \
    src/demo/i18n/FormatPrecedenceDemo.java
cp resources/demo/i18n/Labels_vi_VN.properties build/demo/i18n/
java -cp build demo.i18n.FormatPrecedenceDemo
~~~

**Windows PowerShell:** thay hai lệnh nhiều dòng bằng một lệnh javac một dòng và dùng **Copy-Item** thay cho **cp** nếu cần.

**Stdout chính xác trên OpenJDK 24.0.2:**

~~~text
defaultFormat=title from class
propertyOnly=title from properties
~~~

**Tại sao gọi clearCache(loader)?** ResourceBundle cache có thể khiến một kết quả đã load bằng format policy cũ được trả lại khi bạn đổi Control ngay trong cùng process. Test xóa cache để cách ly hai nhánh. **Không dùng clearCache trên đường xử lý request của ứng dụng thường xuyên**; nó tác động nhiều bundles dùng chung loader và có thể gây overhead.

## 10. ResourceBundle cache và tính nhất quán của Control

ResourceBundle cache các bundle để giảm lookup và I/O. Vì vậy:

- Đổi file .properties trong thư mục nhưng process không thấy ngay là hiện tượng có thể xảy ra.
- Chuyển giữa **FORMAT_DEFAULT** và **FORMAT_PROPERTIES** cho cùng base name/loader mà không kiểm soát cache có thể trả bundle theo format đã tải ở lượt trước.
- Tài liệu Control yêu cầu **getFormats** và **getCandidateLocales** giữ tính nhất quán qua các lần gọi **getBundle** cho cùng base bundle; nếu không có thể xảy ra kết quả bất ngờ.
- Khi cần hot reload, xét policy TTL/reload phù hợp hoặc deployment restart, không nhất thiết phải gọi **clearCache()** liên tục.
- Custom Control khi được dùng đồng thời phải thread-safe.
- Trong hệ thống có plugin classloaders, lookup chỉ thấy các tài nguyên mà classloader/module tương ứng có thể truy cập.

**getFormats(...)** không là một bảng dịch key; nó mô tả các dạng bundle được phép nạp. **getCandidateLocales(...)** không tải bundle; nó mô tả thứ tự locales. Chỉ **getBundle(...)** mới thực hiện lookup, nạp và gắn parent chain.

## 11. Named modules khác ví dụ classpath

**ResourceBundle.Control** được thiết kế cho ứng dụng trong **unnamed module/classpath**. Các overload **ResourceBundle.getBundle(..., Control)** khi được gọi từ **named module** sẽ ném **UnsupportedOperationException** theo contract JDK hiện đại.

Ví dụ chính của bài cố ý chạy qua **java -cp** (unnamed module), nên được phép dùng:

~~~java
ResourceBundle.getBundle(baseName, locale, loader, control);
~~~

Nếu chuyển sang JPMS/named module, xem các overload nhận **Module**, ví dụ:

~~~java
// Mảnh minh họa trong chương trình có module hợp lệ.
ResourceBundle bundle =
        ResourceBundle.getBundle(baseName, requestedLocale, targetModule);
~~~

Với providers nằm trong modules, có cơ chế **java.util.spi.ResourceBundleProvider**, **ServiceLoader** và module declarations tương ứng. Không máy móc sao chép Control example từ classpath vào named module; còn phải xét đóng gói tài nguyên, encapsulation và module access.

**Định dạng properties và class vẫn được hỗ trợ.** Sự khác biệt nằm ở cơ chế tìm/nạp và quyền truy cập khi ứng dụng được module hóa, không phải vì ResourceBundle trở thành API cũ.

## 12. Thực hành kiểm tra candidates và key fallback

### 12.1. Trường hợp chỉ có language bundle

Nếu xóa **Messages_vi_VN.properties** khỏi một thư mục output sạch nhưng vẫn giữ **Messages_vi.properties**, requested **vi-VN** có thể chọn bundle **vi**. Hãy in:

~~~java
// Mảnh code minh họa.
System.out.println(bundle.getLocale().toLanguageTag());
~~~

Kỳ vọng với tập file này và Control của ví dụ là **vi**, không phải vi-VN. Đây là **bundle locale fallback**.

### 12.2. Root fallback và default locale

Nếu chỉ còn **Messages.properties**, requested vi-VN có thể nhận root. Nhưng với Control mặc định và JVM default locale có một bundle khả dụng, loader có thể thử default locale trước khi quyết định dùng root.

Trong bài test dùng **getNoFallbackControl(FORMAT_PROPERTIES)** để mọi máy đều không thử một default locale bất ngờ. **Không kết luận rằng control đó bỏ root**: ở bài test fr-CA, root vẫn được trả về.

### 12.3. Key fallback

Nếu selected bundle vi-VN không có key **sharedVi**, **getString("sharedVi")** sẽ tìm qua parent vi. Nếu không có ở vi nhưng có root, loader có thể lấy root. **getLocale()** trên selected bundle không thay đổi chỉ vì một key có nguồn parent.

### 12.4. Không có key ở bất kỳ đâu

**MissingResourceException** khi gọi **getString** nên được xử lý theo chính sách app: fail-fast ở test/CI, thông báo lỗi có ngữ cảnh trong dev, hoặc fallback sản phẩm có kiểm soát nếu nghiệp vụ cho phép. Không âm thầm trả chuỗi rỗng và che mất key chưa được dịch.

## 13. Lỗi hay gặp và chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| **MissingResourceException** khi getBundle | Base name sai, resource không đóng gói, thiếu candidate/root | Xem resource path trong artifact, tên base, classloader |
| **MissingResourceException** khi getString | Key không có ở selected bundle và parents | Kiểm tra các file candidate và root |
| Sửa .properties nhưng vẫn thấy text cũ | Class bundle ưu tiên, ResourceBundle cache hoặc file chưa được copy vào JAR | In formats, kiểm tra compiled class cùng locale, cache và artifact |
| Java chọn ngôn ngữ mặc định của máy | Default-locale fallback hoạt động | Xem Locale.getDefault, Control.getFallbackLocale, actual getLocale |
| vi-VN bị chọn thành vi | Không có bundle vi-VN hoặc suffix file sai | Kiểm tra candidate list và tên Messages_vi_VN.properties |
| File Messages_vi-VN.properties không được tìm thấy | Dùng dấu gạch nối BCP47 thay vì tên resource | Dùng Messages_vi_VN.properties |
| Chỉ có root và nghĩ mọi key đã dịch | Root dùng fallback cho bundle hoặc key | Kiểm tra locale/key coverage rõ ràng |
| Ký tự tiếng Việt hiển thị sai | Resource bytes sai encoding hoặc terminal output không hỗ trợ | Kiểm tra nội dung UTF-8 trong artifact và kết quả Java String |
| Cùng locale có .class và .properties | FORMAT_DEFAULT ưu tiên class | Chọn format policy nhất quán, bỏ trùng nếu không cần |
| FORMAT_PROPERTIES không có tác dụng | Kết quả từ cache trước đó | Tách test hoặc clearCache trong test; thống nhất policy production |
| Không chạy được Control overload trong named module | API không hỗ trợ Control từ named module | Dùng module-aware ResourceBundle API/providers |
| KeySet iteration khác nhau giữa lần chạy | Không có contract sắp xếp khóa theo ý muốn | Sort key riêng nếu cần output có thứ tự xác định |
| Resource có trong src nhưng thiếu ở runtime | Chưa copy resources vào classpath/JAR | Sửa build pipeline/resource task |
| Kết quả khác giữa CI và laptop | Locale.getDefault, classloader, artifact hoặc cache khác | Ghim locale policy/test và kiểm tra runtime environment |

### Quy trình chẩn đoán thực tế

1. Ghi lại **baseName** và **requestedLocale.toLanguageTag()**.
2. Dùng Control đang áp dụng để in **getCandidateLocales(...)**.
3. In **getFormats(baseName)** và kiểm tra class hay properties được ưu tiên.
4. Xác nhận resources/classes **thật sự có trong artifact runtime**.
5. Dùng **bundle.getLocale()** để biết locale đã chọn.
6. Nếu value sai, kiểm tra parent chain và key; đừng chỉ kiểm tra selected locale.
7. Với fallback bất ngờ, xem **Locale.getDefault()** và Control.getFallbackLocale(...).
8. Nếu content thay đổi mà không reload, xem cache/TTL và quá trình deployment.
9. Với JPMS, kiểm tra overload và quyền đọc resources trong module.
10. Viết regression test với locale + keys + encoding đúng tình huống lỗi.

## 14. Tính toàn vẹn dịch thuật và phát hành

ResourceBundle fallback rất hữu ích vì app có thể hiển thị một thông điệp từ parent khi locale-specific file chưa đủ key. Nhưng đó có thể che thiếu sót dịch thuật nếu test chỉ kiểm tra ứng dụng không crash.

Một bộ test localization nên định nghĩa:

- **Locale hỗ trợ chính thức** (ví dụ vi-VN, en-US) và locale chỉ fallback.
- Các **keys bắt buộc** phải tồn tại trong mỗi locale.
- Có được phép fallback lên root hay không với từng nhóm key.
- Kiểu dữ liệu, placeholder MessageFormat và format có tương thích qua các ngôn ngữ không.
- Encoding đúng cho mọi resource files sau đóng gói.
- Không có key trùng/typo, resource thiếu hoặc class bundle che file properties.
- Khi bổ sung locale script hoặc variant, candidate lists có phản ánh nhu cầu không.

**getString(key) thành công không đồng nghĩa key có bản dịch ở locale yêu cầu**; để đo translation completeness cần kiểm tra nguồn lực cụ thể theo một quy trình QA riêng.

## 15. Bài tập tự luyện

1. Với ví dụ chính, đổi requested locale từ vi-VN sang vi và in **getLocale()** cùng các keys từ parents.
2. Tạm loại **Messages_vi_VN.properties** khỏi **build output sạch**. Dự đoán selected locale và so sánh với kết quả.
3. Giữ root, bỏ vi, vi-VN, yêu cầu fr-CA. Dùng no-fallback Control để xác minh root được chọn.
4. Thêm **Messages_en.properties** và một JVM test có default en-US, so sánh Control mặc định với no-fallback Control để hiểu default-locale fallback.
5. In **getCandidateLocales** cho vi-VN, en-US, zh-Hant-TW, và một locale có variant. Giải thích vì sao script có thể tạo candidates không thể suy đơn giản từ tag.
6. Chạy ví dụ thứ hai với cả **Labels_vi_VN.class** và **Labels_vi_VN.properties**. Bỏ bước clearCache và quan sát khả năng cached bundle ảnh hưởng kết quả.
7. Thêm các keys **login=Đăng nhập**, **logout=Đăng xuất** vào UTF-8 properties. Đọc chúng và kiểm thử dưới JDK 17+.
8. Đóng gói resources vào JAR; xác minh đường dẫn **demo/i18n/Messages_vi_VN.properties** tồn tại trong artifact.
9. Tạo một candidate locale mới không có file, thử truy xuất key chỉ có ở root và một key hoàn toàn thiếu; phân biệt bundle fallback với MissingResourceException.
10. Thiết kế bảng test translation completeness cho ít nhất hai locale, bảo đảm không đánh đồng root fallback với bản dịch hoàn chỉnh.
11. Chuyển một ứng dụng thử nghiệm sang named module và nghiên cứu overload getBundle dùng **Module** thay cho Control.

## 16. Checklist áp dụng

- [ ] Base name không chứa suffix locale hoặc extension .properties.
- [ ] Resource path theo package và được copy vào runtime classpath/JAR đúng vị trí.
- [ ] Locale tạo bằng API rõ ràng (ví dụ Locale.forLanguageTag), không nối chuỗi tự chế.
- [ ] Biết requested locale và actual loaded locale là hai giá trị khác nhau.
- [ ] Hiểu thứ tự candidates; test locale có script/variant khi cần.
- [ ] Chọn policy class/properties rõ, không tạo bundle hai định dạng cùng tên ngoài chủ đích.
- [ ] File properties tiếng Việt lưu UTF-8 và đọc đúng trong JDK được hỗ trợ.
- [ ] Biết getNoFallbackControl không xóa root và parent chain.
- [ ] Có root bundle hoặc policy thiếu locale minh bạch.
- [ ] Phân biệt thiếu bundle với thiếu key và có diagnostic phù hợp.
- [ ] Không dựa vào default JVM locale ngầm trong test yêu cầu tính ổn định.
- [ ] Kiểm soát cache và policy reload; không clearCache mỗi request.
- [ ] Dùng module-aware APIs khi ứng dụng là named module.
- [ ] Không đưa secret vào resource bundle; chỉ nạp artifacts đáng tin.
- [ ] Test source, output/JAR, stdout tiếng Việt, required keys và các trường hợp fallback.

## Kết luận

**ResourceBundle.getBundle(...)** phối hợp **baseName → candidate locales → format selection → fallback locale → parent chain**. Với vi-VN, danh sách thông thường là **vi-VN → vi → root**; với zh-Hant-TW, script/region tạo nhiều bước hơn. **FORMAT_DEFAULT** ưu tiên bundle class trước properties cho cùng candidate. **FORMAT_PROPERTIES** giới hạn vào resource text; **getNoFallbackControl** chỉ vô hiệu hóa default-locale fallback, không cắt root hoặc parent-key lookup.

Trên Java 17+, ResourceBundle dạng properties có thể dùng **UTF-8 tiếng Việt trực tiếp**. Hãy kiểm tra resource paths trong artifact thực, dùng **getCandidateLocales/getFormats/getLocale** để chẩn đoán, và giữ cache/locale policy nhất quán để ứng dụng bản địa hóa đúng trên nhiều máy.

**Tham khảo API chính thức còn áp dụng:**

- [ResourceBundle — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html)
- [ResourceBundle.Control — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.Control.html)
- [PropertyResourceBundle — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [ListResourceBundle — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ListResourceBundle.html)
- [Locale — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html)
- [ResourceBundleProvider — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/ResourceBundleProvider.html)