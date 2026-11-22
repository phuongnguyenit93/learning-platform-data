# Thứ tự nạp CSS và quy tắc ghi đè kiểu dáng trong Javadoc (Java 10+)

## 1. Mục tiêu của bài học

`javadoc` là công cụ của JDK dùng source Java và các **documentation comments** để sinh tài liệu API dạng HTML. **Standard doclet** tạo cấu trúc HTML, navigation, bảng thành viên và những **stylesheet CSS** điều khiển màu sắc, phông chữ, khoảng cách, trạng thái hover/focus, cách hiển thị trên màn hình và khi in.

Một nhu cầu thường gặp là thay màu thương hiệu hoặc kích cỡ chữ trong Javadoc nhưng **giữ nguyên layout, navigation và các quy tắc accessibility đang hoạt động**. Tại đây xuất hiện hai câu hỏi:

1. **Javadoc nạp stylesheet theo thứ tự nào?** Khi dùng một hoặc nhiều tùy chọn `--add-stylesheet`, file nào xuất hiện trước/sau stylesheet mặc định?
2. **Nếu nhiều rule cùng áp dụng, rule nào thắng?** Có phải cứ nạp sau là luôn ghi đè được mọi thứ?

Câu trả lời phải xét **hai tầng**:

- **Tầng Javadoc:** standard doclet chọn và liên kết các tệp CSS trong HTML sinh ra.
- **Tầng trình duyệt:** thuật toán **CSS cascade** quyết định giá trị cuối cho từng property dựa trên origin, `!important`, cascade layer, specificity và source order.

Kiến thức này đã có ý nghĩa từ **Java 10**, vì tài liệu `javadoc` của JDK 10 đã mô tả cả `--add-stylesheet` và `--main-stylesheet`. Các tùy chọn đó **vẫn có trong Oracle JDK 25/26**, nên không cần dựa vào các cách tùy biến doclet đã lỗi thời. Đối với cấu trúc CSS và tên biến trong Javadoc hiện đại, cần tham chiếu **đúng JDK đang tạo docs** thay vì giả định HTML/CSS của mọi phiên bản giống hệt nhau.

Sau bài này, bạn sẽ biết:

- Dùng `--add-stylesheet` để **bổ sung** CSS mà không bỏ stylesheet mặc định.
- Dùng `--main-stylesheet` để **thay thế** stylesheet chính, và hiểu khi nào không nên làm thế.
- Đọc thứ tự các `<link rel="stylesheet">` trong HTML đầu ra.
- Giải thích trường hợp **cùng specificity thì rule xuất hiện sau thắng**, cùng các ngoại lệ quan trọng.
- Dùng **CSS custom properties** của Javadoc như `--body-font-size`, `--link-color` để đổi theme ít phụ thuộc DOM.
- Tạo chương trình Java, hai tệp CSS và tài liệu Javadoc **độc lập, có thể chạy trên JDK 17+**.
- Chẩn đoán lỗi CSS không áp dụng do selector, specificity, asset path, cache, chế độ dark/light, media query hoặc thiếu file.
- Xây một quy trình kiểm thử Javadoc có thể lặp lại trong CI.

## 2. Javadoc sinh ra những gì?

Luồng tối giản:

~~~text
src/example/docs/Greeting.java
       |
       |  javadoc + standard doclet
       v
site/
  index.html
  example/docs/Greeting.html
  resource-files/
      stylesheet.css
      01-brand.css
      02-overrides.css
      ... các resource khác do doclet tạo
       |
       |  Browser đọc HTML + CSS
       v
Trang API được trình bày theo CSS cascade
~~~

Đây là **cấu trúc minh họa được kiểm chứng với OpenJDK 24**. Tên và vị trí một số resources được phép thay đổi giữa bản JDK; **không hard-code đường dẫn nội bộ** của generated docs làm giao diện tích hợp ổn định.

Javadoc không “chọn màu cuối cùng” cho một thẻ HTML. Nó tạo tài liệu có những liên kết đến CSS. **Trình duyệt** mới là nơi thực thi cascade, tính giá trị cuối cho `color`, `font-size`, `background-color`, v.v.

**Ví dụ:**

~~~html
<link rel="stylesheet" href="../../resource-files/stylesheet.css">
<link rel="stylesheet" href="../../resource-files/01-brand.css">
<link rel="stylesheet" href="../../resource-files/02-overrides.css">
~~~

Nếu các style rules liên quan cùng origin, cùng layer, cùng importance và cùng specificity, khai báo từ file được liên kết **sau** có thể thắng. Nhưng nếu selector cũ mạnh hơn, hoặc có `!important`, không được mặc định rule mới thắng.

## 3. Hai tùy chọn cấu hình CSS hiện hành

### 3.1. `--add-stylesheet`: thêm vào mặc định

Ví dụ:

~~~bash
javadoc -d site --add-stylesheet css/01-brand.css src/example/docs/Greeting.java
~~~

Ý nghĩa:

- Standard doclet vẫn tạo/liên kết stylesheet mặc định.
- File `css/01-brand.css` được thêm vào bộ CSS đầu ra.
- CSS bổ sung có thể **ghi đè có chọn lọc** các property của theme mặc định.
- Không cần sao chép toàn bộ stylesheet gốc vào repository.
- Đây là **lựa chọn nên ưu tiên** khi chỉ đổi brand colors, fonts, spacing hoặc một số khu vực nhỏ.

Tài liệu Oracle Javadoc CSS Themes mô tả chính mục tiêu này: tạo custom theme bằng cách **bổ sung** một stylesheet và chỉ override phần cần thiết.

### 3.2. `--main-stylesheet`: thay thế stylesheet chính

Ví dụ:

~~~bash
javadoc -d site --main-stylesheet css/full-theme.css src/example/docs/Greeting.java
~~~

Ý nghĩa:

- CSS mặc định của Javadoc bị **thay** bởi `full-theme.css` ở vị trí stylesheet chính.
- File thay thế **phải chịu trách nhiệm** cho các style/layout cần thiết của toàn bộ tài liệu.
- Nếu tệp chỉ có `:root { --link-color: ...; }`, bạn có thể mất layout, font sizing, navigation, bảng hoặc các hiệu ứng mà stylesheet gốc định nghĩa.
- Dùng khi dự án thật sự cần một theme toàn diện và có quy trình kiểm thử nhiều trang/phiên bản JDK.

`--main-stylesheet` là hình thức được Oracle man page khuyến nghị. Dạng viết khác `-stylesheetfile` cũng được hỗ trợ trong tài liệu, nhưng ví dụ mới nên ưu tiên tên `--main-stylesheet` rõ ràng hơn.

### 3.3. So sánh cách chọn

| Mục tiêu | Tùy chọn hợp lý | Ghi chú |
| --- | --- | --- |
| Đổi link color | `--add-stylesheet` | Giữ nguyên CSS mặc định |
| Tăng font size | `--add-stylesheet` | Ưu tiên CSS variable tương ứng |
| Thêm một lớp theme cho dark/light mode | `--add-stylesheet` | Kiểm thử đủ môi trường |
| Điều chỉnh một vài selectors | `--add-stylesheet` | Tránh phụ thuộc cấu trúc HTML quá sâu |
| Thay toàn bộ visual design | `--main-stylesheet` | Cần CSS đầy đủ, bảo trì cùng JDK |
| Thay main CSS và bổ sung lớp override cuối | Kết hợp hai tùy chọn | Kiểm tra thứ tự trong HTML generated |
| Chỉ đổi một vùng code samples | `--add-stylesheet` | Dùng selector/variables tối thiểu |
| Cần đổi nội dung/DOM của Javadoc | Không phải CSS | Chỉnh doc comments/doclet/template phù hợp |

**Không dùng** việc thay stylesheet chính như cách sửa mọi vấn đề style. Tùy chỉnh nhỏ nên bổ sung CSS để tiếp tục được hưởng các bản sửa tương thích, responsive và accessibility của Javadoc.

## 4. Nạp nhiều stylesheet: thứ tự thực tế

`--add-stylesheet` có thể được truyền nhiều lần:

~~~bash
javadoc -d site   --add-stylesheet css/01-brand.css   --add-stylesheet css/02-overrides.css   src/example/docs/Greeting.java
~~~

Với **OpenJDK 24**, kiểm thử thực tế cho thấy trong trang class `example/docs/Greeting.html`:

~~~html
<link rel="stylesheet" type="text/css"
      href="../../resource-files/jquery-ui.min.css" title="Style">
<link rel="stylesheet" type="text/css"
      href="../../resource-files/stylesheet.css" title="Style">
<link rel="stylesheet" type="text/css"
      href="../../resource-files/01-brand.css" title="Style">
<link rel="stylesheet" type="text/css"
      href="../../resource-files/02-overrides.css" title="Style">
~~~

Thứ tự rút ra:

1. Có thể có resource CSS phục vụ thành phần giao diện của Javadoc, ví dụ `jquery-ui.min.css` ở bản đã kiểm thử.
2. **`stylesheet.css`** là stylesheet chính mặc định.
3. **`01-brand.css`** được liên kết sau stylesheet chính.
4. **`02-overrides.css`** được liên kết sau `01-brand.css`.

Javadoc đã **sao chép cả hai stylesheet tùy chỉnh** vào thư mục output `resource-files`. Khi HTML class nằm trong thư mục package con, đường dẫn `../../resource-files/...` là tương đối so với vị trí của trang.

**Không khẳng định** mọi JDK đều tạo thêm chính xác `jquery-ui.min.css`, giữ đúng tên resource directory hoặc có cùng số lượng link. Những chi tiết này **là quan sát của JDK 24**, không phải giao diện public bất biến. Hãy kiểm tra HTML generated của JDK đang dùng.

### 4.1. Kết hợp main stylesheet với additional stylesheets

Lệnh:

~~~bash
javadoc -d site   --main-stylesheet css/full-theme.css   --add-stylesheet css/01-brand.css   --add-stylesheet css/02-overrides.css   src/example/docs/Greeting.java
~~~

Ở **OpenJDK 24**, kết quả quan sát được là stylesheet chính `full-theme.css` nằm ở vị trí thay cho `stylesheet.css`, sau đó tới `01-brand.css`, `02-overrides.css`.

~~~text
... CSS resources nội bộ của Javadoc ...
full-theme.css
01-brand.css
02-overrides.css
~~~

Phối hợp này hữu ích cho cấu trúc **base theme → brand → local overrides**, nhưng đừng tự thêm nhiều lớp nếu chỉ cần một file CSS đơn giản.

### 4.2. “Nạp sau” không có nghĩa mạng tải xong sau

CSS **source order** là thứ tự stylesheet được đặt trong tài liệu HTML và vị trí các rules tương ứng, **không phải** ai tải xuống xong trước trên mạng. Một request CSS có thể hoàn tất sớm/muộn vì cache hoặc kết nối, nhưng browser vẫn sử dụng **vị trí của stylesheet trong document order** khi xét trường hợp source order có ý nghĩa.

Đừng dùng `setTimeout`, script hoặc sửa ngẫu nhiên thứ tự network requests để chữa cascade; hãy kiểm tra `<head>` và CSS rules.

## 5. CSS cascade: phải xét những lớp ưu tiên nào?

Khi **hai hoặc nhiều declarations** cùng nhắm tới một property của cùng phần tử, trình duyệt không chỉ xét “dòng nào ở cuối”. Quy trình CSS cascade hiện hành có thể tóm tắt:

1. **Relevance:** rule có áp dụng không (selector, `@media`, `@supports`, scope)?
2. **Origin và importance:** browser/user/author styles và `!important` hay không.
3. **Cascade layers:** thứ tự `@layer`, kể cả khác biệt cho normal và important declarations.
4. **Specificity:** độ ưu tiên selector, ví dụ ID, class, type.
5. **Scoping proximity:** khi dùng `@scope` và các mức trên bằng nhau, xét khoảng tới scope root.
6. **Source order:** nếu vẫn ngang nhau, khai báo có thứ tự xuất hiện **sau** thắng.

Đây là các yếu tố **thuộc tiêu chuẩn CSS**, không phải thuật toán đặc biệt chỉ có trong Javadoc.

### 5.1. Trường hợp đơn giản: cùng selector, cùng layer, cùng importance

File được liên kết trước:

~~~css
/* 01-brand.css */
:root {
    --body-font-size: 15px;
    --link-color: #145a83;
}
~~~

File được liên kết sau:

~~~css
/* 02-overrides.css */
:root {
    --body-font-size: 17px;
    --link-color: #7b1fa2;
}
~~~

Trong cả hai file:

- Selector là cùng một `:root`.
- Cả hai nằm ở author origin, mặc định không có layer riêng, không `!important`.
- Chúng định nghĩa cùng custom properties trên cùng root element.

Vì vậy ở trường hợp bình thường, **file nạp sau thắng do source order**:

~~~text
--body-font-size = 17px
--link-color      = #7b1fa2
~~~

Kết quả được áp dụng tới những nơi stylesheet của Javadoc **sử dụng** các biến đó bằng `var(...)`. Nếu CSS của phiên bản JDK đã thay cách dùng biến, cần kiểm tra lại computed styles thay vì chỉ đọc tên biến.

### 5.2. Specificity mạnh hơn có thể thắng dù nạp trước

~~~css
/* 01-brand.css */
.content-container a {
    color: #aa2200;
}
~~~

~~~css
/* 02-overrides.css */
a {
    color: #0044aa;
}
~~~

Nếu một link nằm trong `.content-container` và cả hai rules khớp:

- `.content-container a`: specificity **0-1-1**.
- `a`: specificity **0-0-1**.

Rule có class + element mạnh hơn, nên màu **#aa2200** có thể thắng dù nằm trong file nạp trước (giả sử cùng origin/layer/importance và không có rule khác).

**Bài học:** Khi CSS cuối file không áp dụng, đừng cứ di chuyển rule xuống dưới; xem **specificity** trong DevTools.

### 5.3. `!important` quan trọng hơn source order thông thường

~~~css
/* Nằm ở file trước */
.example-link {
    color: #a00000 !important;
}
~~~

~~~css
/* Nằm ở file sau */
.example-link {
    color: #0055aa;
}
~~~

Ở cùng origin/layer, declaration có `!important` thắng declaration normal dù nó xuất hiện trước.

Nhưng không nên “sửa” mọi thứ bằng việc thêm `!important` vào toàn bộ custom CSS. Cách đó dễ làm hỏng theme, accessibility, dark mode và maintenance. Hãy hiểu nguyên nhân, chọn đúng selector/custom property và chỉ dùng `!important` khi có lý do rõ ràng.

### 5.4. Cascade layers làm thay đổi cách so thứ tự

CSS hiện hành hỗ trợ:

~~~css
@layer base {
    .example-link {
        color: #a00000;
    }
}

.example-link {
    color: #0055aa;
}
~~~

Với **normal declarations**, style **không ở layer** thường được ưu tiên **hơn** style nằm trong một layer thông thường, ngay cả khi layer có selector mạnh hơn. Nếu hai normal rules ở các layers khác nhau, **layer khai báo sau** được ưu tiên; với `!important`, thứ tự layers **đảo chiều**.

Đối với Javadoc, nếu bạn bắt đầu dùng `@layer` để quản lý theme, hãy lập **layer order** rõ ràng và kiểm tra cả những rules mặc định vốn có thể chưa thuộc layer. Đừng chỉ suy luận “file của tôi tải sau, nên mọi thứ ở file đó cao nhất”.

### 5.5. Inline styles và việc kế thừa giá trị

HTML có thể có:

~~~html
<p style="color: #111111">Ví dụ</p>
~~~

Trong nhiều tình huống bình thường, inline style ở **author origin** ưu tiên hơn normal external stylesheet declaration cùng property. CSS inheritance còn có nghĩa một property trực tiếp trên phần tử có thể thắng giá trị được **kế thừa** từ parent, dù selector đặt ở parent nhìn có vẻ mạnh.

Javadoc standard doclet thường sinh rất nhiều HTML có class names và cấu trúc riêng. **Không dựa vào inline styles trong doc comments để tùy biến theme toàn cục**: khó bảo trì và có thể làm tài liệu không đáp ứng accessibility hoặc policy của tổ chức.

## 6. CSS custom properties: cách override ít rủi ro

Javadoc hiện đại sử dụng **CSS custom properties** cho màu sắc và typography. Trong Oracle Javadoc CSS Themes Guide, các ví dụ được khai báo tại `:root` để có thể được thừa kế bởi nhiều phần tử:

~~~css
:root {
    --body-font-size: 17px;
    --body-font-family: system-ui, sans-serif;
    --link-color: #145a83;
    --body-background-color: #ffffff;
    --body-text-color: #202124;
}
~~~

Một số custom properties được hướng dẫn của Javadoc liệt kê:

| Biến | Mục tiêu |
| --- | --- |
| `--body-font-family` | Font của văn bản thường |
| `--code-font-family` | Font hiển thị code |
| `--body-font-size` | Kích cỡ chữ nền |
| `--code-font-size` | Kích cỡ chữ code |
| `--body-background-color` | Màu nền chính |
| `--body-text-color` | Màu chữ chính |
| `--link-color` | Màu liên kết |
| `--link-color-active` | Màu link ở một số trạng thái |
| `--navbar-background-color` | Nền của navigation |
| `--navbar-text-color` | Chữ trên navigation |
| `--section-background-color` | Nền các vùng nội dung |
| `--table-border-color` | Màu viền bảng |
| `--snippet-background-color` | Nền đoạn snippet/code |

Những tên trên đến từ **hướng dẫn Javadoc CSS themes chính thức**, và trong thí nghiệm JDK 24, `stylesheet.css` có `--body-font-size` cùng `--link-color`. Tuy nhiên **theme variables không phải Java source API ổn định mãi mãi**. Khi nâng JDK, nên tái kiểm tra stylesheet mặc định và các vùng hiển thị thực sự dùng từng biến.

### 6.1. Vì sao `:root` phù hợp?

`:root` chọn root element của HTML, thường là `html`, với specificity **0-1-0**. Đặt biến trên root giúp nó có thể được **kế thừa** bởi các phần tử con. Nếu Javadoc theme có:

~~~css
a {
    color: var(--link-color);
}
~~~

thì custom CSS:

~~~css
:root {
    --link-color: #145a83;
}
~~~

có thể đổi màu liên kết mà không cần biết toàn bộ selector cho các navigation/content links.

**Nhưng:** nếu có selector khác đặt `color` tường minh trên link với ưu tiên cao hơn, hoặc một CSS variable khác được dùng trong trạng thái cụ thể, đổi `--link-color` đơn lẻ không nhất thiết thay được mọi link.

### 6.2. Custom property có phụ thuộc scope

~~~css
:root {
    --link-color: #145a83;
}

.special-section {
    --link-color: #b30050;
}
~~~

Một link nằm trong `.special-section` có thể dùng giá trị `--link-color` được định nghĩa lại tại vùng đó do **inheritance**, không nhất thiết dùng root value. Vì vậy đừng nhìn mỗi `:root` rồi kết luận màu computed của tất cả link đều giống nhau.

### 6.3. Dùng `var()` với giá trị dự phòng

Ví dụ ở custom CSS riêng:

~~~css
.example-callout {
    border-color: var(--table-border-color, #aab3bb);
}
~~~

Nếu `--table-border-color` không có giá trị hợp lệ theo cascade cho phần tử, fallback được dùng. Tuy nhiên fallback **không thay** việc kiểm tra tương thích: một variable đã được khai báo nhưng có giá trị không hợp lệ ở nơi sử dụng có thể dẫn tới kết quả khác dự định.

## 7. Ví dụ hoàn chỉnh: source Java, hai CSS files, tài liệu HTML

### 7.1. Cấu trúc project

Tạo các tệp sau:

~~~text
javadoc-css-demo/
  src/
    example/
      docs/
        Greeting.java
  css/
    01-brand.css
    02-overrides.css
  classes/        (tạo khi biên dịch)
  site/           (Javadoc tạo)
~~~

Tên `01-brand.css`, `02-overrides.css` được đặt có chủ ý: dễ hiểu **vai trò** và **thứ tự mong muốn**, tránh trùng tên khi doclet sao chép vào output.

### 7.2. Source Java thực sự chạy được

File **`src/example/docs/Greeting.java`**:

~~~java
package example.docs;

/**
 * A greeting utility used to demonstrate Javadoc CSS rules.
 */
public final class Greeting {

    /** Prevents instantiation. */
    private Greeting() {}

    /**
     * Builds a greeting.
     *
     * @param name name to greet
     * @return greeting text
     */
    public static String message(String name) {
        return "Hello, " + name + "!";
    }

    /**
     * Runs the example.
     *
     * @param args unused command-line arguments
     */
    public static void main(String[] args) {
        System.out.println(message("Java 10"));
    }
}
~~~

Chương trình này chỉ dùng cú pháp Java thông dụng và có thể chạy trên **JDK 17+**. Javadoc comments được viết đầy đủ, gồm `@param`/`@return`, nên có thể bật **DocLint** khi sinh tài liệu mà không cần tắt kiểm tra chất lượng.

### 7.3. CSS file thứ nhất: brand variables

File **`css/01-brand.css`**:

~~~css
:root {
    --body-font-size: 15px;
    --link-color: #145a83;
}
~~~

File này là **lớp brand ban đầu**. Nó không copy lại layout Javadoc, không đụng vào internal DOM class names.

### 7.4. CSS file thứ hai: override có chủ đích

File **`css/02-overrides.css`**:

~~~css
:root {
    --body-font-size: 17px;
    --link-color: #7b1fa2;
}
~~~

Vì file thứ hai dùng **cùng selector `:root`** và cùng CSS properties ở cùng origin/layer/importance, khi liên kết sau, nó có ưu tiên source order cao hơn file đầu. Điều này tạo một thí nghiệm dễ kiểm chứng mà không phải dựa vào một CSS class nội bộ có thể thay tên ở JDK tiếp theo.

### 7.5. Biên dịch và chạy chương trình

Từ thư mục `javadoc-css-demo`:

~~~bash
javac -d classes src/example/docs/Greeting.java
java -cp classes example.docs.Greeting
~~~

**Stdout chính xác:**

~~~text
Hello, Java 10!
~~~

Đã kiểm chứng thực tế trên OpenJDK 24. Phần này kiểm tra Java program, **không** tự kiểm tra tính đúng của trang CSS.

### 7.6. Sinh tài liệu Javadoc với cả hai stylesheets

~~~bash
javadoc -Werror -Xdoclint:all -encoding UTF-8   -d site   --add-stylesheet css/01-brand.css   --add-stylesheet css/02-overrides.css   src/example/docs/Greeting.java
~~~

Trên **Bash/sh**, ký tự `\` cuối dòng có tác dụng nối dòng. **Trên Windows PowerShell**, không dùng ký tự nối dòng kiểu Bash; hãy viết cả lệnh trên một dòng:

~~~powershell
javadoc -Werror -Xdoclint:all -encoding UTF-8 -d site --add-stylesheet css/01-brand.css --add-stylesheet css/02-overrides.css src/example/docs/Greeting.java
~~~

Giải thích các tùy chọn:

| Phần lệnh | Tác dụng |
| --- | --- |
| `-d site` | Đặt thư mục đầu ra, thường được javadoc tạo |
| `--add-stylesheet css/01-brand.css` | Thêm CSS thứ nhất |
| `--add-stylesheet css/02-overrides.css` | Thêm CSS thứ hai |
| `-encoding UTF-8` | Đọc source theo UTF-8; hữu ích với comments tiếng Việt |
| `-Xdoclint:all` | Kiểm tra các nhóm DocLint cho tài liệu HTML |
| `-Werror` | Coi cảnh báo Javadoc là lỗi build |
| `src/example/docs/Greeting.java` | Source cần sinh docs |

Lệnh đã được chạy thành công với **OpenJDK 24**: `javac` trả exit code 0, `java` in đúng stdout, `javadoc -Werror -Xdoclint:all` trả exit code 0 và sao chép đủ stylesheet mặc định cùng hai stylesheet custom. Đây là kết quả kiểm chứng **cú pháp sinh tài liệu và cấu trúc file**, không phải phép đo trực tiếp màu pixel trong browser.

### 7.7. Mở và kiểm tra tài liệu

Trang class được sinh ra ở vị trí:

~~~text
site/example/docs/Greeting.html
~~~

Trên hệ điều hành có browser, mở file đó hoặc phục vụ `site/` qua một HTTP server nội bộ phù hợp. Trong phần **View Source** hoặc DevTools Elements, tìm các `<link rel="stylesheet">`:

~~~text
... stylesheet.css ...
... 01-brand.css ...
... 02-overrides.css ...
~~~

Trên OpenJDK 24, hai custom stylesheets được copy vào:

~~~text
site/resource-files/01-brand.css
site/resource-files/02-overrides.css
~~~

Đây là **địa chỉ thực nghiệm** của bản đã kiểm tra. Nếu bạn dùng JDK khác, hãy để **HTML generated dẫn đường** tới file CSS tương ứng.

## 8. Xác định rule nào thắng trong ví dụ

Các khai báo đối nghịch:

| Property | 01-brand.css | 02-overrides.css | Kết quả cascade dự kiến |
| --- | --- | --- | --- |
| `--body-font-size` | `15px` | `17px` | **`17px`** |
| `--link-color` | `#145a83` | `#7b1fa2` | **`#7b1fa2`** |

**Điều kiện:** cùng selector `:root`, cùng origin, cùng cascade layer, không có declaration `!important` hoặc CSS rule khác có ưu tiên cao hơn. Custom property values được chọn từ source order, sau đó những CSS declarations `var(--body-font-size)`/`var(--link-color)` mới sử dụng các giá trị đã tính.

Muốn chứng minh bằng browser:

1. Mở `Greeting.html`.
2. Trong DevTools, chọn phần tử **`html`** và xem **Computed/Styles** để tìm `--body-font-size`, `--link-color`.
3. Mở `01-brand.css` và `02-overrides.css` trong tab Sources/Network để xác nhận đúng nội dung.
4. Xem rule `:root` của file cuối có ghi đè declaration cùng property trong file trước không.
5. Chọn body hoặc một link cụ thể, xem property computed thật (ví dụ `font-size`, `color`) để xác nhận **nơi đó** có sử dụng variable hay có CSS rule khác can thiệp.
6. Nếu chưa thấy kết quả, kiểm tra `@media`, cascade layers, rule specificity và browser cache.

**Không đồng nhất:** “Root variable bằng #7b1fa2” với “Mọi link đều buộc phải có màu #7b1fa2”. Một selector direct `color` khác hoặc dark-mode rule phù hợp có thể tác động tới một số link.

## 9. Thay thứ tự hai file: điều gì thay đổi?

Thử đảo:

~~~bash
javadoc -d site-reversed   --add-stylesheet css/02-overrides.css   --add-stylesheet css/01-brand.css   src/example/docs/Greeting.java
~~~

Trong Javadoc hiện hành, khi HTML generated liên kết CSS theo thứ tự đối nghịch, **`01-brand.css`** trở thành file xuất hiện sau. Với cùng `:root` selectors và các điều kiện cascade bằng nhau, kết quả dự kiến đổi thành:

~~~text
--body-font-size = 15px
--link-color      = #145a83
~~~

Đây là một phép thử rất hữu ích để minh họa **source order**. Nếu kết quả computed vẫn không thay đổi, điều đó cho thấy có thể còn yếu tố CSS khác hoặc trình duyệt đang dùng tài nguyên đã cache. Đừng kết luận javadoc “bỏ qua file” khi chưa kiểm tra HTML links và Network.

### Tránh xây nhiều CSS files không cần thiết

Nếu một dự án chỉ cần thay hai biến, một file:

~~~css
:root {
    --body-font-size: 17px;
    --link-color: #7b1fa2;
}
~~~

với một `--add-stylesheet` là đủ, dễ bảo trì hơn. Hai file trong bài được dùng để **làm rõ thứ tự và ghi đè**, không phải một yêu cầu bắt buộc của Javadoc.

## 10. Dùng `--main-stylesheet` đúng cách

Thử nghiệm:

~~~bash
javadoc -d site-full   --main-stylesheet css/full-theme.css   --add-stylesheet css/02-overrides.css   src/example/docs/Greeting.java
~~~

`full-theme.css` **phải là stylesheet đầy đủ**, có các quy tắc layout/typography cần thiết. Không dùng một CSS chỉ chứa vài declarations `:root` rồi mong tài liệu tự giữ mọi style của `stylesheet.css` mặc định.

### 10.1. Hướng làm theme toàn diện

1. Sinh bộ docs mẫu bằng chính **JDK đang triển khai**.
2. Xem stylesheet chính mà Javadoc sinh ra.
3. Nếu cần thay hoàn toàn, lấy nó làm **điểm xuất phát để chỉnh có kiểm soát** theo giấy phép/quy trình của dự án; không giả định cấu trúc CSS bất biến giữa các JDK.
4. Thiết lập `--main-stylesheet` trỏ tới file đầy đủ.
5. Chạy **DocLint**, kiểm tra index/package/class pages, search UI, detail/summary tables, dark/light, narrow viewport và print.
6. Khi cập nhật JDK, so các thay đổi stylesheet HTML/CSS của JDK rồi cập nhật theme tương ứng.

### 10.2. Một ví dụ sai về mặt thiết kế

~~~css
/* Không đủ để THAY toàn bộ stylesheet mặc định: */
:root {
    --link-color: #7b1fa2;
}
~~~

Nếu chỉ cần đổi màu, dùng **`--add-stylesheet`**, không dùng `--main-stylesheet` với file thiếu layout.

### 10.3. Kết hợp main và added CSS

Nếu dùng đầy đủ main stylesheet cùng added CSS, các **added** stylesheets trong JDK 24 được liên kết sau main stylesheet. Nhưng **một selector mạnh trong main** hoặc `!important` vẫn có thể thắng một selector yếu trong added CSS. Thứ tự link không tạo một quyền ưu tiên tuyệt đối.

## 11. `@import` khác `--add-stylesheet` ra sao?

Bạn cũng có thể dùng CSS `@import`:

~~~css
@import url("./tokens.css");

:root {
    --link-color: #145a83;
}
~~~

Theo CSS, một `@import` hợp lệ được xử lý trong **source order tại vị trí khai báo import**. Nó thường phải nằm trước các style rules thông thường (ngoại lệ hạn chế như `@charset` và một số `@layer` statements theo chuẩn).

**Nhưng trong Javadoc build** có một bẫy:

- `--add-stylesheet` sao chép những CSS files được chỉ định vào generated output.
- Nếu custom CSS chứa `@import "./tokens.css"`, trình duyệt sẽ tìm `tokens.css` **tương đối với URL của bản CSS đã được sao chép**.
- Javadoc **không nhất thiết tự tìm và đóng gói mọi file** được `@import`, `url(...)` hay font rules tham chiếu.
- Nếu file phụ không xuất hiện ở vị trí URL mới, browser nhận 404/ERR_FILE_NOT_FOUND và style không như mong đợi.

Cách làm rõ ràng nhất trong ví dụ này là đưa mỗi CSS file trực tiếp qua `--add-stylesheet`. Nếu cần ảnh/font/CSS bổ sung, hãy thiết kế bước **copy assets** trong build pipeline và kiểm tra URL thực trên site xuất bản.

**Không nhầm** `@import` với option của Javadoc: một cái là CSS rule do browser xử lý, cái kia là tham số cho **doclet**.

## 12. Specificity: bảng quyết định thực dụng

Trong các ví dụ sau, giả định **cùng author origin, không `@layer` riêng, không animation/transition và không `!important`**.

| Selector | Độ ưu tiên specificity |
| --- | --- |
| `a` | `0-0-1` |
| `.member-signature` | `0-1-0` |
| `:root` | `0-1-0` |
| `.content a` | `0-1-1` |
| `#details a` | `1-0-1` |

Ba phần thường được biểu diễn dưới dạng **ID – class/attribute/pseudo-class – type/pseudo-element**.

Ví dụ:

~~~css
/* Nạp trước nhưng mạnh hơn */
.content a {
    color: #b00020;
}

/* Nạp sau nhưng yếu hơn */
a {
    color: #145a83;
}
~~~

Nếu hai selectors cùng match, `.content a` có specificity cao hơn, nên declaration đầu có thể thắng.

Khi debug, hãy trả lời tuần tự:

1. Selector của file custom có thực sự khớp phần tử?
2. Property đó có bị rule khác **important** không?
3. Có cascade layer nào thay đổi ưu tiên không?
4. Specificity giữa hai rules chênh lệch ra sao?
5. Nếu các mức bằng nhau, rule nào ở **sau** trong source order?
6. Property là **direct value** hay một value dùng `var(...)` kế thừa từ parent?

**Đừng tăng specificity một cách ngẫu nhiên** bằng selectors rất dài hoặc lặp ID: có thể giải quyết một trang nhưng tạo khó khăn bảo trì khi Javadoc đổi DOM.

## 13. Khi chỉnh màu, hãy kiểm tra accessibility và dark mode

Javadoc mặc định được xây dựng với nhiều mục tiêu về khả năng đọc và accessibility. Một brand stylesheet nên bảo toàn:

- **Text contrast:** chữ/links dễ đọc trên nền sáng/tối.
- **Keyboard focus visibility:** link và control còn có dấu hiệu focus rõ ràng.
- **Hover/active/visited:** trạng thái vẫn phân biệt được, không chỉ dựa vào một màu.
- **Text scaling:** tăng font size không làm cắt chữ/bảng.
- **Responsive:** navigation và bảng không tràn vùng nhìn trên màn hình nhỏ.
- **Print:** tài liệu vẫn dễ đọc khi in PDF/từ browser.
- **High contrast/forced colors:** không ép màu làm mất thông tin.
- **Reduced motion:** tránh hiệu ứng chuyển động không cần thiết.

Một CSS ví dụ theo chế độ màu (chỉ thêm nếu được dự án kiểm thử):

~~~css
@media (prefers-color-scheme: dark) {
    :root {
        --body-background-color: #202124;
        --body-text-color: #f1f3f4;
        --link-color: #9ecbff;
    }
}
~~~

Điều này **không bảo đảm** ghi đè mọi biến/cấu trúc dark theme của Javadoc hiện tại. Nếu Javadoc cũng có các media rules riêng, cần xem **Computed styles** trong browser với `prefers-color-scheme` thực tế. Không dùng một màu chữ cố định rồi bỏ qua màu nền, vì sẽ làm giảm contrast.

**Cảnh báo bảo mật:** không chèn script hoặc HTML không tin cậy vào doc comments chỉ để thay CSS. Javadoc tạo tài liệu HTML từ source, và nội dung không phù hợp có thể ảnh hưởng tính an toàn của site docs. CSS chỉ nên lấy từ source/build assets được kiểm soát.

## 14. Các lỗi CSS thường gặp trong Javadoc

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không thấy custom CSS trong HTML | Lệnh `javadoc` thiếu `--add-stylesheet` hoặc build dùng option khác | Kiểm tra effective build args và HTML `<head>` |
| HTML có link nhưng CSS 404 | File không được copy hoặc relative path sai | Kiểm tra `href`, file trong output và deployment |
| Biến root thay nhưng link không đổi | Rule cụ thể đặt `color` khác, hoặc dùng biến khác | DevTools Computed/Styles ở link thật |
| File cuối không thắng file trước | Specificity, `!important`, layers hoặc media | Đọc đầy đủ cascade |
| `--main-stylesheet` làm layout mất | CSS thay thế không chứa base rules | Dùng `--add-stylesheet` cho override nhỏ |
| Màu chỉ đổi ở một vài trang | DOM/selector khác hoặc CSS asset thiếu ở nested path | Test index, package, class và member detail |
| Cùng trang nhưng dark mode khác | Media query và theme-specific variables | Thử light/dark và xem computed styles |
| Browser hiển thị CSS cũ | Cache hoặc site CDN chưa cập nhật | Hard reload/disable cache và kiểm tra network response |
| CSS bị ghi đè khi nâng JDK | Theme default vars/selector đổi | Diff stylesheet generated và test lại |
| CSS `@import` không tác dụng | Relative imported file không được triển khai | Copy assets/kiểm tra URL thật |
| Có hai file cùng tên | Collision khi copy tới resource location, cấu hình dễ nhầm | Dùng tên duy nhất, tránh duplicate basenames |
| UI mất focus ring | Override `:focus`/`:focus-visible` không phù hợp | Khôi phục keyboard focus affordance |
| Link có contrast kém | Brand color quá sát màu nền | Đo contrast cả normal/hover/visited |
| Công cụ `javap` được dùng thay `javadoc` | Chọn sai JDK tool | `javap` đọc class files, `javadoc` tạo HTML docs |
| Style thay nhưng package docs cũ | Site build/deploy copy nhầm thư mục | Clean output, xác minh artifact publish |

Để tránh lỗi stale artifacts, trong CI hãy **sinh docs vào output directory sạch của build hiện tại**. Tuy nhiên **không xóa bừa thư mục** nếu đó là một đường dẫn dùng chung hoặc chứa tài liệu quan trọng; chỉ làm sạch đúng build output đã được xác định.

## 15. Debug CSS từ DevTools theo một trình tự tin cậy

**Bước 1 — kiểm tra HTML thực được mở.** Ở trang class cần debug, mở View Source/Elements và tìm thứ tự các `<link rel="stylesheet">`. Nếu file không có link, đó là vấn đề của Javadoc/build, chưa phải specificity.

**Bước 2 — kiểm tra resource thực tải.** Trong tab Network, tìm `stylesheet.css`, `01-brand.css`, `02-overrides.css`. Xác nhận status/response body. Khi chạy offline qua `file://`, hành vi tải font/resource hoặc CORS có thể khác HTTP deployment, nên kiểm thử thêm trên site được phục vụ đúng cách.

**Bước 3 — xem computed styles.** Chọn phần tử `html`, body và link đang có vấn đề. Xem declaration nào áp dụng và declaration nào bị gạch bỏ; DevTools thường hiển thị file, line và nguyên nhân override.

**Bước 4 — phân biệt biến và thuộc tính thực.** Nếu `--link-color` đã đúng nhưng `color` của link sai, tìm rule trực tiếp của link hoặc custom property shadow ở một ancestor.

**Bước 5 — kiểm tra các điều kiện.** Toggle light/dark, media width, zoom và keyboard focus. Một rule `@media print` sẽ không áp dụng trong chế độ screen, dù nằm trong file cuối.

**Bước 6 — kiểm tra kết quả build với browser thật.** Một lần `javadoc` exit code 0 chỉ xác nhận sinh tài liệu thành công; **không đủ** để nói màu hiện ra đúng, contrast đạt yêu cầu hoặc bố cục không tràn.

**Bước 7 — ghi lại cách sửa.** Khi đã thấy lý do override, ưu tiên thay đổi **custom properties/selector tối thiểu**, không thêm `!important` ở nhiều nơi để che vấn đề.

## 16. Cấu hình lệnh Javadoc trong CI và build systems

Lệnh tổng quát cho một Java module đơn giản:

~~~bash
javadoc -Werror -Xdoclint:all -encoding UTF-8   -d build/api-docs   --add-stylesheet css/01-brand.css   --add-stylesheet css/02-overrides.css   src/example/docs/Greeting.java
~~~

Với project thực, có thể sinh theo package, source path hoặc module path; cấu hình cụ thể phụ thuộc Maven, Gradle hoặc hệ thống build. Điểm cần bảo đảm:

1. **JDK version** của CI và developer thống nhất/được ghi lại.
2. **CSS files được version hóa**, có sẵn ở đúng working directory.
3. **Arguments giữ đúng thứ tự**, nhất là nhiều `--add-stylesheet`.
4. `-d` trỏ tới **đúng output artifact** sẽ publish.
5. CI kiểm tra **warnings**, HTML links, sự tồn tại của tài nguyên CSS.
6. Có ít nhất một kiểm thử browser/visual khi thay theme hoặc nâng JDK.
7. Khi thay stylesheet mặc định, có regression tests về navigation, search, package/class/member pages.
8. Không giả định plugin build tự truyền options theo đúng thứ tự nếu chưa kiểm tra effective command line.

**Lưu ý về Maven/Gradle:** cú pháp plugin thay đổi giữa phiên bản plugin, nên bài này không bịa một snippet plugin có thể đã lỗi thời. Hãy kiểm tra tài liệu **phiên bản plugin đang cài** để ánh xạ `--add-stylesheet` vào task Javadoc, và xác nhận command/output thực được tạo.

### 16.1. Test file existence và source order

Với dự án ví dụ:

~~~text
site/example/docs/Greeting.html
site/resource-files/stylesheet.css
site/resource-files/01-brand.css
site/resource-files/02-overrides.css
~~~

Có thể kiểm tra output:

~~~bash
test -f site/example/docs/Greeting.html
test -f site/resource-files/01-brand.css
test -f site/resource-files/02-overrides.css
~~~

Lệnh `test -f` dành cho Unix shell. Trên PowerShell:

~~~powershell
Test-Path site/example/docs/Greeting.html
Test-Path site/resource-files/01-brand.css
Test-Path site/resource-files/02-overrides.css
~~~

**Cần kiểm tra cả thứ tự trong HTML** thay vì chỉ file tồn tại. Ví dụ, đọc các `link` elements trong `Greeting.html` và đối chiếu thứ tự tên file. Tránh viết regex dựa tuyệt đối vào mọi attribute của `<link>` vì Javadoc có thể thay formatting hoặc thêm attributes giữa các JDK.

### 16.2. Cảnh báo là lỗi build

`-Werror` hữu ích nếu muốn giữ Javadoc sạch warnings, nhưng không thay thế kiểm tra nội dung web. `-Xdoclint:all` sẽ phát hiện nhiều lỗi documentation comments; đầu ra `javadoc` vẫn có thể chứa lỗi CSS không phải lỗi Java/DocLint.

## 17. Những quy tắc ghi đè nên/không nên dùng

| Nên | Không nên |
| --- | --- |
| Giữ stylesheet mặc định bằng `--add-stylesheet` nếu chỉ đổi vài property | Dùng `--main-stylesheet` với CSS vài dòng rồi làm mất layout |
| Dùng `:root` variables được Javadoc tài liệu hóa | Sao chép selectors nội bộ quá dài mà không kiểm tra phiên bản |
| Đặt một file override cuối khi cần layers rõ ràng | Dựa vào thứ tự download network |
| Kiểm tra CSS cascade toàn diện | Kết luận “nạp sau luôn thắng” |
| Giữ contrast, focus, responsiveness | Dùng `!important` tràn lan |
| Dùng tên CSS không trùng | Có nhiều file cùng basename trong output |
| Kiểm tra generated HTML và CSS assets | Chỉ dựa vào thành công của `javac` hoặc `javadoc` |
| Kiểm tra lại sau nâng JDK | Coi Javadoc CSS class names và vars bất biến |
| Kiểm thử nhiều trang + browser | Chỉ nhìn một screenshot index |
| Đóng gói thêm assets cần thiết khi dùng `@import` | Giả định doclet tự copy mọi file được CSS tham chiếu |

## 18. Tình huống: override một màu nhưng kết quả không đổi

Giả sử bạn thêm:

~~~css
/* custom.css - liên kết sau default */
a {
    color: #0055aa;
}
~~~

Nhưng màu navigation links không đổi. Các hướng điều tra:

1. **Selector không khớp**: navigation link có thể dùng rule khác.
2. **Specificity**: Javadoc default có selector cụ thể hơn, ví dụ class + descendant.
3. **State**: link ở trạng thái `:hover`, `:active`, `:visited` hoặc focus với rule khác.
4. **Custom property**: theme có thể dùng `var(--navbar-text-color)`, không phải `--link-color`.
5. **Media query**: người dùng đang ở dark mode, browser áp một set variables khác.
6. **Layer/importance**: file custom không nằm trong origin/layer priority như bạn tưởng.
7. **Cache**: browser chưa tải bản CSS mới.
8. **Missing copy**: site được publish thiếu `custom.css`.

Một cách sửa ít phụ thuộc DOM hơn là xác định Javadoc theme dùng biến nào cho vùng đó, rồi override custom property phù hợp:

~~~css
:root {
    --navbar-text-color: #f5f7ff;
    --navbar-background-color: #243b63;
}
~~~

Sau đó kiểm tra link trong navigation có contrast phù hợp và các state còn hiển thị rõ. **Không mặc định** hai biến này giải quyết mọi cấu trúc navigation của mọi JDK — vẫn cần kiểm chứng trên bản đang dùng.

## 19. Câu hỏi tự kiểm tra

### Câu 1 — lựa chọn tùy chọn

**Hỏi:** Chỉ muốn đổi font size và link color nhưng giữ layout Javadoc. Nên chọn `--add-stylesheet` hay `--main-stylesheet`?

**Đáp án:** **`--add-stylesheet`**, vì bổ sung CSS mà giữ mặc định. `--main-stylesheet` thay thế toàn bộ main CSS và cần theme đủ đầy.

### Câu 2 — thứ tự hai CSS files

`01-brand.css` và `02-overrides.css` cùng khai báo `:root { --body-font-size: ... }` không `!important` hay layer đặc biệt. File nào thắng nếu Javadoc link 01 trước, 02 sau?

**Đáp án:** **02-overrides.css**, do source order khi các mức cascade khác bằng nhau.

### Câu 3 — không phải luôn nạp sau thắng

File trước có `.content a { color: red; }`, file sau có `a { color: blue; }`; link nằm trong `.content`. Có chắc màu xanh không?

**Đáp án:** **Không.** `.content a` có specificity cao hơn nên có thể thắng.

### Câu 4 — `!important`

File trước khai báo `a { color: red !important; }`, file sau `a { color: blue; }`. Ở cùng origin/layer, màu nào thắng?

**Đáp án:** **Đỏ**, vì important thắng normal. Không cần chuyển file.

### Câu 5 — CSS variables

`--link-color` đã đổi thành tím trong Computed styles trên root, nhưng một link vẫn xanh. Có phải Javadoc không nhận CSS mới?

**Đáp án:** Không nhất thiết. Link có thể có **direct color declaration** hoặc custom property override khác. Kiểm tra computed `color` của chính link.

### Câu 6 — Javadoc 10 và JDK hiện nay

`--add-stylesheet` chỉ có thể dùng trong Java 10 và đã bị bỏ từ Java 11?

**Đáp án:** **Không.** Nó có trong tài liệu JDK 10 và vẫn hiện diện ở Oracle JDK 25/26.

### Câu 7 — thứ tự nạp và mạng

Một CSS file tải xong nhanh hơn có được browser xếp cuối source order hay không?

**Đáp án:** **Không.** Source order do vị trí rules trong stylesheet/HTML imports/links quyết định, không phải thời điểm network completion.

### Câu 8 — `--main-stylesheet`

Nếu chỉ cung cấp `:root { --link-color: purple; }` với `--main-stylesheet`, có bảo đảm Javadoc giữ nguyên mọi layout mặc định không?

**Đáp án:** **Không.** Main CSS mặc định đã bị thay, nhiều layout/style khác có thể mất.

### Câu 9 — `@import`

File custom được Javadoc copy tới `resource-files/custom.css`; bên trong có `@import "./colors.css"`. Browser tìm `colors.css` ở đâu?

**Đáp án:** **Tương đối với URL của custom.css được copy**, không phải đường dẫn source CSS ban đầu. Phải đảm bảo colors.css được đóng gói ở đúng nơi.

### Câu 10 — vấn đề cache

HTML có đúng link và server đã update CSS, nhưng browser hiển thị giá trị cũ. Bước tiếp theo?

**Đáp án:** Xem Network response của file CSS, kiểm tra cache, hard reload/disable cache và nguồn site thực đang mở.

### Câu 11 — màu dark mode

Một custom theme chỉ kiểm thử light mode. Có thể khẳng định đạt accessibility ở dark mode không?

**Đáp án:** **Không.** Phải kiểm tra các `@media`, computed color/background, contrast và các trạng thái focus/hover.

### Câu 12 — kiểm thử Java và Javadoc

Lệnh `java -cp classes example.docs.Greeting` cho `Hello, Java 10!`. Có chứng minh CSS override đã hiện màu tím không?

**Đáp án:** **Không.** Chạy Java kiểm tra logic program; CSS cần kiểm tra generated HTML, assets và browser Computed styles riêng.

## 20. Checklist cuối bài

- [ ] Xác định đúng **JDK version** và standard doclet đang sử dụng.
- [ ] Chọn `--add-stylesheet` nếu chỉ cần thêm CSS; dùng `--main-stylesheet` khi có theme đầy đủ.
- [ ] Nếu nhiều CSS files, đặt tên không trùng và truyền options theo thứ tự có chủ đích.
- [ ] Kiểm tra HTML generated có `stylesheet.css`/main CSS và added files theo thứ tự mong muốn.
- [ ] Kiểm tra CSS files đã được copy tới output và URLs của các trang nested package truy cập được.
- [ ] Khi CSS không áp dụng, xét **origin, importance, layers, specificity, scope và source order**.
- [ ] Ưu tiên Javadoc **CSS custom properties** trước khi override internal selectors.
- [ ] Không coi `!important` là giải pháp mặc định.
- [ ] Không coi tải file từ network nhanh/chậm là source order.
- [ ] Kiểm tra `@import`/`url(...)` sau khi copy stylesheet vào output.
- [ ] Chạy `javadoc -Werror -Xdoclint:all` với source comments đúng cú pháp.
- [ ] Kiểm tra Java stdout **và** generated HTML/CSS bằng các phép thử khác nhau.
- [ ] Test index, package, class, method detail, search/navigation, mobile, print, dark/light, keyboard focus.
- [ ] Sau khi đổi JDK hoặc build plugin, kiểm tra lại effective CSS variable names và site asset paths.
- [ ] Bảo vệ accessibility/contrast, không chèn script hoặc external CSS không đáng tin vào tài liệu.

## 21. Tóm tắt

- **Thứ tự từ Javadoc:** stylesheet chính được nạp trước, các `--add-stylesheet` được nạp sau theo thứ tự đã kiểm chứng ở OpenJDK 24; `--main-stylesheet` thay stylesheet chính.
- **Thứ tự từ CSS:** “rule đến sau thắng” chỉ đúng khi mọi yếu tố cascade ưu tiên cao hơn **đã bằng nhau**. Specificity, important, layers và scope có thể thay đổi kết quả.
- **Chiến lược khuyến nghị:** giữ CSS mặc định và chỉnh **custom properties** qua `--add-stylesheet`, vì ít làm hỏng cấu trúc tài liệu hơn việc thay toàn bộ stylesheet.
- **Quy trình kiểm chứng:** chạy code Java → sinh docs → kiểm tra HTML link order + CSS files → kiểm tra computed styles trên browser → kiểm tra accessibility và regression khi nâng JDK.
- Các ví dụ **đã được kiểm chứng bằng OpenJDK 24**: Java stdout `Hello, Java 10!`; `javadoc -Werror -Xdoclint:all` exit 0; các file CSS được copy; link order main stylesheet → 01-brand → 02-overrides. Trình duyệt mới là nơi xác minh visual outcome chính xác.

## 22. Tài liệu tham khảo chính thức

1. [Oracle Java 10 — javadoc tool options](https://docs.oracle.com/javase/10/tools/javadoc.htm) — xác nhận `--add-stylesheet`, `--main-stylesheet` đã được tài liệu hóa.
2. [Oracle JDK 25 — The javadoc Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html) — cú pháp và hành vi các tùy chọn hiện hành.
3. [Oracle JDK 26 — The javadoc Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html) — đối chiếu bản phát hành mới.
4. [Oracle Javadoc CSS Themes Guide (JDK 22)](https://docs.oracle.com/en/java/javase/22/javadoc/programmers-guide-javadoc-css-themes.html) — CSS custom properties, override so với replace.
5. [MDN — Introduction to the CSS cascade](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Cascade/Introduction) — relevance, origin, importance, layers, specificity, scope và order.
6. [MDN — CSS specificity](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Cascade/Specificity) — cách tính selector priority.
7. [MDN — CSS cascade layers](https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Styling_basics/Cascade_layers) — normal/important layer ordering.
8. [MDN — CSS `@import`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/%40import) — imported stylesheet và file URL resolution.
9. [WHATWG HTML — The `link` element](https://html.spec.whatwg.org/multipage/semantics.html#the-link-element) — HTML liên kết external stylesheets.
10. [W3C CSS Cascading and Inheritance](https://www.w3.org/TR/css-cascade-5/) — chuẩn CSS cascade.

**Kết luận:** muốn kiểm soát kiểu dáng Javadoc, hãy **kiểm tra thứ tự `<link>` mà doclet thật sự sinh ra**, bổ sung CSS qua **`--add-stylesheet`**, và áp dụng đầy đủ **CSS cascade** trước khi kết luận rule nào ghi đè. Một file được liên kết sau chỉ thắng rule trước khi những yếu tố như `!important`, layer, specificity và scoping không còn phân biệt. Đây là cách tạo theme ít lỗi và bảo trì được khi nâng JDK.
