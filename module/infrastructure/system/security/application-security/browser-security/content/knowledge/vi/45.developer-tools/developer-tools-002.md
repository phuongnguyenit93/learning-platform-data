# Source map: hiểu ánh xạ mã đã build về mã nguồn khi debug

Source map là tệp dữ liệu mô tả cách các vị trí trong mã JavaScript hoặc CSS đã được build tương ứng với vị trí trong những tệp nguồn ban đầu. Nhờ source map, DevTools có thể hiển thị mã dễ đọc hơn, đặt breakpoint theo mã nguồn và ánh xạ stack trace về dòng đã viết trong dự án.

Trong ứng dụng web, source map cũng là một vấn đề cần xem xét về bảo mật. Nếu bản đồ được phát hành công khai và chứa nội dung nguồn, người truy cập có thể xem lại phần lớn mã nguồn trước khi bundler minify hoặc transpile. Source map không tự thực thi mã và không thay thế bất kỳ cơ chế bảo vệ nào của browser; rủi ro chính thường là lộ thông tin mà bản build production không định chủ ý công khai.

Bài học này đặt source map trong quy trình build và debug của trình duyệt, giải thích cấu trúc Source Map v3, cách DevTools tải bản đồ, các chế độ tạo map phổ biến, cách quản lý map trong production và quy trình kiểm tra để tránh phát hành nhầm mã nguồn nội bộ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao bundler, transpiler và minifier tạo ra nhu cầu dùng source map.
- Mô tả cách DevTools dùng source map để hiển thị mã nguồn, breakpoint và stack trace.
- Nhận diện chỉ thị sourceMappingURL trong JavaScript và CSS.
- Đọc các trường quan trọng trong một source map dạng JSON.
- Phân biệt external, inline, hidden và no-sources source map.
- Hiểu source map có thể tiết lộ mã nguồn, cấu trúc thư mục và thông tin triển khai như thế nào.
- Phân biệt việc ẩn đường dẫn tới map với việc kiểm soát quyền truy cập map.
- Cấu hình build và pipeline phát hành để giữ source map ở nơi phù hợp.
- Kiểm tra bundle, map URL, CDN và artifact production.
- Khắc phục lỗi DevTools không tải hoặc ánh xạ source map chính xác.

## 1. Vì sao cần source map?

Mã nguồn ứng dụng thường trải qua nhiều bước trước khi browser thực thi:

1. Developer viết JavaScript, TypeScript, JSX hoặc mã CSS.
2. Công cụ build có thể chuyển cú pháp mới về cú pháp tương thích, loại bỏ type, ghép module và tối ưu mã.
3. Minifier rút gọn tên biến, xóa khoảng trắng và biến đổi biểu thức.
4. Browser tải các bundle đã tạo và thực thi chúng.

Ví dụ, mã ban đầu có thể dễ đọc:

~~~javascript
export function calculateTotal(items) {
  return items.reduce((sum, item) => {
    return sum + item.price * item.quantity;
  }, 0);
}
~~~

Sau khi minify, đoạn mã có thể trở thành:

~~~javascript
function n(e){return e.reduce((n,t)=>n+t.price*t.quantity,0)}
~~~

Khi lỗi xảy ra trong bundle, stack trace có thể trỏ tới một dòng rất dài hoặc tên hàm khó hiểu. Developer phải lần ngược từ mã đã biến đổi để tìm đoạn mã ban đầu.

Source map cung cấp ánh xạ giữa vị trí trong bundle và vị trí trong source. Khi DevTools nhận được bundle cùng map tương ứng, nó có thể trình bày vị trí lỗi theo tệp và dòng gần với mã developer đã viết.

~~~mermaid
flowchart TD
    A["Mã nguồn: TypeScript, JSX, CSS"] --> B["Transpile và bundle"]
    B --> C["Minify / tối ưu"]
    C --> D["Bundle production"]
    B --> E["Thông tin ánh xạ"]
    C --> E
    E --> F["Source map"]
    D --> G["Browser thực thi bundle"]
    D --> H["DevTools đọc bundle"]
    F --> H
    H --> I["Hiển thị vị trí trong source"]
~~~

Source map phục vụ việc gỡ lỗi và quan sát mã. Browser vẫn thực thi bundle đã tải; source map không thay bundle bằng mã nguồn ban đầu.

### 1.1 Source map không phải bản sao chạy được của ứng dụng

Source map là dữ liệu mô tả quan hệ vị trí. Nó không phải một runtime, không phải module loader và không làm browser thực thi lại TypeScript hoặc JSX.

Nếu xóa source map nhưng giữ nguyên bundle, ứng dụng thường vẫn chạy như trước. Developer có thể mất khả năng xem mã nguồn gốc và stack trace có thể khó đọc hơn, nhưng logic thực thi của bundle không tự thay đổi.

### 1.2 Source map không phải source code protection

Minify làm mã khó đọc hơn nhưng không mã hóa mã nguồn. Người dùng vẫn có thể tải bundle và phân tích nó. Nếu source map công khai chứa trường sourcesContent, việc xem lại mã nguồn ban đầu trở nên thuận tiện hơn nhiều.

Không nên xem minification, obfuscation hoặc việc bỏ source map là cách giữ bí mật cho khóa API, mật khẩu hay thuật toán cần được bảo vệ. Mọi dữ liệu gửi xuống browser đều phải được xem là có thể bị người dùng phân tích.

## 2. Source map được DevTools sử dụng như thế nào?

Một quy trình thường gặp gồm ba thành phần:

- Bundle JavaScript hoặc CSS được browser tải.
- Chỉ thị hoặc metadata cho biết vị trí source map.
- Tệp map mô tả ánh xạ về source ban đầu.

Với JavaScript, bundle thường kết thúc bằng một chú thích như:

~~~javascript
//# sourceMappingURL=app.8f31c2.js.map
~~~

Với CSS, chỉ thị thường nằm trong comment:

~~~css
/*# sourceMappingURL=app.8f31c2.css.map */
~~~

Khi DevTools mở bundle và hỗ trợ source map, công cụ tìm chỉ thị này, phân giải URL map theo vị trí của tài nguyên được tải rồi đọc dữ liệu ánh xạ. DevTools có thể hiển thị các source đã được ánh xạ trong khu vực Sources và dùng map để diễn giải stack trace hoặc breakpoint.

Cách tải map và các giới hạn truy cập có thể khác nhau theo browser, phiên bản DevTools, cấu hình máy chủ và cách công cụ build phát hành artifact. Hãy kiểm thử trên browser mục tiêu thay vì suy luận rằng một header CORS hoặc CSP cụ thể luôn có cùng tác động trong mọi công cụ.

### 2.1 Bundle và map phải thuộc cùng một bản build

Giả sử browser tải bundle phiên bản A nhưng URL source map lại trả map phiên bản B. DevTools có thể hiển thị dòng sai, đặt breakpoint không khớp hoặc ánh xạ stack trace đến một đoạn code khác.

Để tránh lỗi này:

- Gắn hash nội dung hoặc version vào tên bundle và map.
- Sinh bundle và map trong cùng một lần build.
- Phát hành chúng như một bộ artifact có cùng release identifier.
- Không ghi đè map của release cũ bằng map của release mới.
- Khi upload map lên dịch vụ theo dõi lỗi, gắn đúng release, commit hoặc build identifier.

### 2.2 URL tương đối và sourceRoot

Giá trị sourceMappingURL thường có thể là đường dẫn tương đối. Đường dẫn đó được phân giải dựa trên URL của tài nguyên chứa chỉ thị. Ví dụ, nếu bundle ở:

~~~text
https://static.example.test/assets/app.js
~~~

và comment chỉ tới:

~~~text
app.js.map
~~~

thì công cụ sẽ tìm map tương ứng trong thư mục assets theo quy tắc phân giải URL.

Trường sourceRoot trong map có thể bổ sung tiền tố cho các đường dẫn nằm trong sources. Nếu sourceRoot hoặc sources chứa đường dẫn nội bộ như thư mục máy developer, tên workspace hoặc cấu trúc repository, chúng có thể làm lộ thông tin về môi trường build.

Không sửa đường dẫn theo phỏng đoán khi map không tải được. Hãy kiểm tra URL cuối cùng trong Network panel, phản hồi HTTP và cấu trúc thư mục thực tế của artifact.

### 2.3 Map không tải được vẫn không nhất thiết làm ứng dụng lỗi

Các tình huống phổ biến:

- Bundle tải thành công nhưng map trả về 404.
- Map bị chặn hoặc không thể truy cập từ môi trường DevTools.
- URL map sai do deploy thay đổi thư mục.
- Map không hợp lệ hoặc không khớp bundle.
- Map không có sourcesContent và source gốc cũng không thể tải.
- DevTools tắt tùy chọn JavaScript hoặc CSS source maps.

Trong nhiều trường hợp, ứng dụng vẫn thực thi bundle bình thường. Vấn đề chủ yếu ảnh hưởng đến trải nghiệm debug.

## 3. Cấu trúc source map

Source Map v3 thường được biểu diễn bằng một object JSON. Ví dụ rút gọn:

~~~json
{
  "version": 3,
  "file": "app.min.js",
  "sourceRoot": "",
  "sources": [
    "src/main.js",
    "src/format.js"
  ],
  "sourcesContent": [
    "export function start() { formatMessage(); }",
    "export function formatMessage() { return 'ready'; }"
  ],
  "names": [
    "start",
    "formatMessage"
  ],
  "mappings": "AAAA,SAASA,KAAK,CAAC"
}
~~~

Giá trị mappings trong ví dụ chỉ mang tính minh họa, không phải một bản đồ hoàn chỉnh có thể dùng cho bundle thật.

| Trường | Ý nghĩa |
|---|---|
| version | Phiên bản định dạng source map; các map phổ biến hiện nay dùng giá trị 3 |
| file | Tên tệp được tạo ra, thường là bundle hoặc stylesheet |
| sourceRoot | Tiền tố tùy chọn dùng khi phân giải đường dẫn source |
| sources | Danh sách đường dẫn hoặc định danh source ban đầu |
| sourcesContent | Nội dung source tương ứng, nếu công cụ build nhúng nội dung |
| names | Danh sách tên định danh có thể được dùng trong ánh xạ |
| mappings | Dữ liệu mã hóa các đoạn ánh xạ giữa vị trí generated và original |

### 3.1 sources

sources liệt kê các tệp nguồn liên quan tới bundle. Đường dẫn có thể là tương đối, có thể kết hợp với sourceRoot và không nhất thiết là đường dẫn filesystem tuyệt đối.

Dù không có nội dung nguồn, danh sách này vẫn có thể tiết lộ:

- Tên module hoặc package nội bộ.
- Cấu trúc thư mục của repository.
- Tên tính năng chưa phát hành.
- Tên tệp chứa logic xác thực hoặc xử lý nghiệp vụ.
- Thông tin về framework và công cụ build.

Đây là metadata có thể hữu ích cho người phân tích ứng dụng. Mức độ nhạy cảm phụ thuộc vào tên và cấu trúc dự án.

### 3.2 sourcesContent

sourcesContent là mảng chứa nội dung source tương ứng với từng phần tử trong sources. Một số công cụ build nhúng mã nguồn vào map để DevTools không cần tải riêng các tệp source ban đầu.

Nếu trường này có mặt trong map công khai, người tải map có thể đọc source ngay trong phản hồi JSON. Đây thường là phần làm tăng đáng kể mức độ lộ mã nguồn.

Nếu không có sourcesContent hoặc một phần tử là null, DevTools có thể không hiển thị nội dung source từ map. Tùy môi trường và URL, công cụ có thể cần tải source riêng; vì vậy việc bỏ sourcesContent không tự bảo đảm source không thể truy cập.

### 3.3 mappings

mappings lưu các đoạn ánh xạ vị trí giữa mã generated và mã original. Dữ liệu thường dùng Base64 VLQ để mã hóa các giá trị chênh lệch, giúp giảm kích thước map.

Không nên sửa mappings thủ công. Một thay đổi nhỏ cũng có thể khiến vị trí dòng, cột, tên symbol hoặc source bị lệch. Hãy để công cụ build tạo lại map từ đúng bundle và source tương ứng.

### 3.4 Indexed source map

Một số quy trình build có thể dùng indexed source map, trong đó các phần ánh xạ được tổ chức theo sections và offset. Dạng này hữu ích khi ghép nhiều phần output. Khi xử lý map bằng công cụ tự viết, cần dùng parser hỗ trợ đúng dạng map thay vì giả định mọi tệp chỉ có một trường mappings đơn giản.

## 4. Các cách phát hành source map

Cần phân biệt nơi map được tạo ra, nơi map được lưu và ai có thể tải map.

### 4.1 External source map

Map được tạo thành tệp riêng, thường có phần mở rộng .map:

~~~text
assets/
  app.8f31c2.js
  app.8f31c2.js.map
~~~

Bundle có thể chứa comment sourceMappingURL trỏ tới tệp map. Cách này dễ kiểm tra và phù hợp với nhiều quy trình phát triển.

Nếu cả bundle và map đều được đưa vào thư mục public, người dùng có thể truy cập map theo URL nếu máy chủ cho phép. Không được mặc định rằng đuôi .map sẽ khiến máy chủ tự bảo vệ tệp.

### 4.2 Inline source map

Inline map được nhúng trong bundle bằng data URL. Một chỉ thị minh họa:

~~~javascript
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjoz...
~~~

Ưu điểm là không cần request riêng để lấy map. Nhược điểm là bundle lớn hơn và nội dung map đi cùng tài nguyên được phát hành. Nếu map chứa sourcesContent, source gốc cũng nằm trong bundle có thể tải xuống.

Inline source map thường phù hợp với môi trường phát triển hoặc một số quy trình kiểm thử. Cần đánh giá kỹ trước khi dùng cho production.

### 4.3 Hidden source map

Một số công cụ có chế độ tạo tệp map nhưng không thêm comment sourceMappingURL vào bundle. Ví dụ, webpack có cấu hình hidden-source-map và Vite có giá trị build.sourcemap là hidden.

Cách này giúp pipeline tạo map để upload lên hệ thống theo dõi lỗi mà bundle không công bố chỉ thị tới map. Tuy nhiên, hidden chỉ mô tả cách tạo output. Nếu tệp .map vẫn nằm trong thư mục public hoặc CDN cho phép tải, người dùng có thể truy cập nó khi biết hoặc đoán URL.

Vì vậy, hidden source map chỉ có ý nghĩa khi bước deploy cũng loại map khỏi vùng public và lưu map trong hệ thống riêng có kiểm soát truy cập.

### 4.4 No-sources source map

Một số công cụ hỗ trợ tạo map không nhúng nội dung source, ví dụ webpack nosources-source-map.

Chế độ này có thể giảm việc lộ nội dung trực tiếp qua sourcesContent, nhưng metadata vẫn có thể cho biết tên tệp, đường dẫn và cấu trúc module. Nếu source URL có thể truy cập độc lập, nội dung vẫn có thể bị tải theo cách khác.

Không dùng no-sources như một cam kết bảo mật tuyệt đối. Hãy kiểm tra chính xác map đã phát hành và quyền truy cập các source liên quan.

### 4.5 So sánh các chế độ

| Chế độ | Map nằm ở đâu? | Có thể lộ source? | Điểm cần kiểm tra |
|---|---|---|---|
| External | Tệp .map riêng | Có, nếu map chứa sourcesContent hoặc source tải được | Quyền truy cập URL map |
| Inline | Nhúng trong bundle | Có, nếu map chứa source | Nội dung bundle công khai |
| Hidden | Tệp riêng, thường không có comment tham chiếu | Có, nếu tệp vẫn public | Quy tắc deploy và CDN |
| No-sources | Tệp riêng, bỏ nội dung source nhúng | Giảm lộ trực tiếp, vẫn lộ metadata | sources, sourceRoot và URL source |
| Không tạo map | Không có map | Không lộ qua map | Bundle vẫn có thể bị phân tích |

## 5. Source map và ranh giới bảo mật của ứng dụng web

Trong phạm vi bảo mật trình duyệt, cần hiểu rõ source map tác động đến tính bí mật của mã client như thế nào và không tác động đến những cơ chế nào khác.

### 5.1 Rủi ro lộ mã nguồn

Nếu source map được công khai và chứa sourcesContent, người ngoài có thể khôi phục nội dung nhiều tệp nguồn. Họ có thể hiểu rõ hơn:

- Cách frontend gọi API và cấu trúc request.
- Tên route, feature flag và chức năng chưa hiển thị trong giao diện.
- Cách client xử lý token hoặc dữ liệu phiên.
- Các điều kiện kiểm tra quyền được viết ở phía client.
- Tên module, thư viện và phiên bản phụ thuộc.
- Comment, thông tin debug và đường dẫn môi trường phát triển.

Mã client vốn có thể được phân tích từ bundle. Source map làm quá trình đó nhanh và rõ ràng hơn. Đây là rủi ro về tiết lộ thông tin và tăng khả năng trinh sát, không tự động đồng nghĩa với việc attacker có quyền truy cập dữ liệu server.

### 5.2 Source map không thay thế authorization

Một ứng dụng không được dựa vào việc người dùng không biết tên API, route hoặc tên hàm để bảo vệ tài nguyên.

Server phải xác thực người gọi và kiểm tra quyền trên từng tài nguyên, hành động và tenant. Việc ẩn source map không sửa được endpoint thiếu authorization. Ngược lại, source map công khai cũng không nên làm lộ dữ liệu mà server đã bảo vệ đúng cách.

### 5.3 Không đưa secret vào mã frontend

Không đặt các giá trị sau trong source code sẽ được bundle xuống browser:

- Private API key hoặc secret dùng server-to-server.
- Database password hoặc signing key.
- Token quản trị dài hạn.
- Credential của dịch vụ nội bộ.
- Khóa mã hóa cần giữ bí mật ở server.

Nếu secret đã nằm trong bundle hoặc sourcesContent được phát hành, xóa map khỏi CDN chưa đủ. Secret cần được xem là đã lộ và xử lý theo quy trình ứng phó tương ứng, bao gồm thu hồi hoặc xoay vòng nếu phù hợp.

### 5.4 Đường dẫn nội bộ và thông tin môi trường

Đường dẫn như ổ đĩa developer, tên user hệ điều hành, tên workspace, hostname nội bộ hoặc tên project có thể xuất hiện trong sources và sourceRoot nếu build tool ghi chúng vào map.

Thông tin này có thể giúp attacker suy đoán công nghệ, tổ chức mã và môi trường build. Dùng đường dẫn tương đối hoặc cấu hình path mapping phù hợp; kiểm tra map thực tế trước khi phát hành.

### 5.5 CORS, CSP và MIME không phải biện pháp giữ kín map public

CORS chủ yếu kiểm soát việc JavaScript từ origin khác đọc response theo mô hình same-origin và CORS. Nó không biến một URL public thành tài nguyên bí mật. Người dùng có thể truy cập URL bằng công cụ HTTP hoặc môi trường khác nếu máy chủ cho phép.

CSP giúp kiểm soát một số nguồn tài nguyên và hành vi của document. CSP không thay thế xác thực và phân quyền ở nơi lưu source map. Cũng không nên dựa vào khác biệt hành vi tải map của DevTools giữa các browser làm ranh giới bảo mật.

Content-Type chính xác và X-Content-Type-Options: nosniff là các cấu hình tốt cho tài nguyên web, nhưng chúng không ngăn người dùng đọc JSON map mà họ đã được phép tải.

Muốn giữ map riêng tư, hãy lưu nó ở kho artifact hoặc dịch vụ error monitoring có xác thực, sau đó chỉ cấp quyền cho pipeline và người cần debug.

### 5.6 Source map không tự tạo XSS

Một source map hợp lệ là dữ liệu mô tả ánh xạ. Việc có một tệp map không tự biến nội dung trong đó thành JavaScript được thực thi trong trang.

Tuy nhiên, source được tiết lộ có thể giúp người kiểm thử nhận ra DOM sink, luồng dữ liệu không tin cậy hoặc logic xử lý HTML. Nếu tìm thấy một điểm yếu XSS trong mã gốc, cần đánh giá và sửa chính điểm yếu đó bằng output encoding, safe DOM APIs, CSP hoặc Trusted Types phù hợp.

Không nên mô tả việc công khai source map là một lỗ hổng XSS nếu chưa có đường thực thi mã cụ thể.

## 6. Cấu hình source map trong quy trình build

Chính sách source map cần được quyết định theo môi trường và mục tiêu vận hành. Môi trường phát triển thường cần map đầy đủ để debug nhanh. Production có thể cần map cho việc giải mã stack trace nhưng không muốn phát hành map công khai.

### 6.1 Webpack

Webpack cung cấp nhiều lựa chọn qua cấu hình devtool. Ví dụ production tạo hidden source map:

~~~javascript
module.exports = {
  mode: "production",
  devtool: "hidden-source-map",
  output: {
    filename: "assets/[name].[contenthash].js"
  }
};
~~~

Trong pipeline này, cần bảo đảm tệp .map được upload tới dịch vụ theo dõi lỗi hoặc kho artifact riêng, còn bước deploy public chỉ đưa các bundle và tài nguyên được phép phát hành lên CDN.

Một số lựa chọn thường gặp:

| Giá trị devtool | Đặc điểm cần hiểu |
|---|---|
| source-map | Tạo map riêng và tham chiếu từ bundle |
| hidden-source-map | Tạo map riêng nhưng không thêm comment tham chiếu |
| nosources-source-map | Không nhúng source content vào map |
| inline-source-map | Nhúng map vào bundle |
| eval-source-map | Thường hướng tới trải nghiệm development, không nên chọn production chỉ vì build nhanh |

Tên chế độ thể hiện hành vi tạo map, không phải policy phân quyền của máy chủ.

### 6.2 Vite

Vite hỗ trợ cấu hình build.sourcemap với các giá trị boolean hoặc chế độ inline/hidden tùy phiên bản và cấu hình build.

Ví dụ:

~~~javascript
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    sourcemap: "hidden"
  }
});
~~~

Cấu hình hidden vẫn có thể tạo tệp .map trong output directory. Pipeline deploy phải lọc hoặc chuyển map sang nơi lưu riêng. Luôn đối chiếu hành vi với phiên bản Vite đang dùng và kiểm tra nội dung thư mục build thực tế.

### 6.3 Phân tách artifact public và private

Một pipeline có thể tổ chức kết quả như sau:

~~~text
build/
  public/
    assets/
      app.8f31c2.js
      app.8f31c2.css
  private/
    sourcemaps/
      app.8f31c2.js.map
      app.8f31c2.css.map
~~~

Bundle được đưa tới CDN hoặc web server. Map được upload tới dịch vụ theo dõi lỗi với release identifier tương ứng.

Đây là ví dụ tổ chức logic; công cụ build có thể tạo output trong một thư mục duy nhất. Điều quan trọng là bước deploy phân loại artifact rõ ràng trước khi publish.

### 6.4 Kiểm soát bước deploy

Pipeline nên có các kiểm tra:

1. Xác định chính sách map cho development, staging và production.
2. Tạo bundle và map từ cùng một commit.
3. Kiểm tra map có sourcesContent hay không.
4. Upload map tới nơi lưu riêng nếu cần symbolication.
5. Chỉ copy artifact public vào thư mục deploy.
6. Kiểm tra thư mục public không chứa file .map ngoài allowlist.
7. Kiểm tra bundle production có comment sourceMappingURL ngoài dự kiến hay không.
8. Kiểm tra URL map cũ trên CDN và cache sau khi phát hành.
9. Gắn release identifier để hệ thống lỗi chọn đúng map.
10. Lưu log phát hành để có thể truy vết artifact.

Đừng chỉ dựa vào tên file hoặc comment cuối bundle. Một map có thể được public dưới URL dễ đoán ngay cả khi bundle không trỏ tới nó.

## 7. Kiểm tra source map bằng DevTools

Thực hiện trong ứng dụng lab hoặc môi trường bạn được phép kiểm thử.

### 7.1 Kiểm tra DevTools có bật source maps

Mở DevTools, vào Settings và tìm phần Sources hoặc Preferences liên quan đến JavaScript source maps và CSS source maps. Tên mục có thể thay đổi theo browser và phiên bản.

Sau đó:

1. Mở trang ứng dụng.
2. Vào Network và tải lại trang.
3. Chọn bundle JavaScript hoặc stylesheet.
4. Kiểm tra response và comment sourceMappingURL nếu có.
5. Quan sát request map trong Network.
6. Mở Sources và tìm source đã được ánh xạ.

Nếu DevTools không hiển thị source gốc, hãy xác minh map có được tạo, URL có đúng và phản hồi map có hợp lệ không.

### 7.2 Kiểm tra lỗi ánh xạ

Khi DevTools báo lỗi source map:

- Xem URL map cuối cùng mà browser yêu cầu.
- Kiểm tra status HTTP như 200, 403 hoặc 404.
- Kiểm tra body có phải JSON source map hợp lệ.
- Xác nhận version và cấu trúc trường.
- Kiểm tra map có khớp bundle đang tải.
- Kiểm tra sourceRoot và các đường dẫn trong sources.
- Kiểm tra source có được nhúng trong sourcesContent hay phải tải riêng.
- Xem console có thông báo parse error hoặc network error không.

Không sửa nội dung map để che lỗi. Hãy tạo lại từ đúng build hoặc sửa URL và pipeline phát hành.

### 7.3 Kiểm tra breakpoint và stack trace

Đặt breakpoint trong source gốc được hiển thị bởi DevTools, thực hiện thao tác gây chạy đoạn code rồi xác nhận debugger dừng ở vị trí mong muốn.

Để kiểm tra stack trace, tạo một lỗi có kiểm soát trong lab. So sánh vị trí khi bật map và khi tắt map. Vị trí sau khi ánh xạ phải trỏ về source và dòng tương ứng của release hiện tại.

Nếu stack trace trỏ sai source, kiểm tra sự lệch phiên bản giữa bundle và map trước khi nghi ngờ debugger.

## 8. Kiểm tra rò rỉ source map trong production

Phần này dành cho domain, CDN và ứng dụng thuộc quyền quản lý của bạn.

### 8.1 Kiểm tra comment trong bundle

Tải bundle production và tìm sourceMappingURL. Ví dụ:

~~~bash
curl -fsS https://static.example.test/assets/app.js -o app.js
grep -n "sourceMappingURL" app.js
~~~

Nếu có comment, ghi lại URL map sau khi phân giải theo URL bundle. Nếu không có comment, vẫn tiếp tục kiểm tra thư mục artifact, manifest deploy và CDN vì map có thể tồn tại mà không được tham chiếu.

### 8.2 Kiểm tra URL map đã biết

Nếu bạn biết URL map từ build artifact hoặc comment:

~~~bash
curl -I https://static.example.test/assets/app.js.map
~~~

Đánh giá status và header. Nếu cần xác nhận body trong lab:

~~~bash
curl -fsS https://static.example.test/assets/app.js.map -o app.js.map
~~~

Không đưa map production chứa mã nội bộ vào công cụ chia sẻ công khai để phân tích. Nếu phải kiểm tra thủ công, dùng máy và nơi lưu trữ được tổ chức cho phép.

### 8.3 Kiểm tra nội dung map

Trong môi trường an toàn, kiểm tra:

- sourcesContent có chứa source hay không.
- sources có đường dẫn nội bộ hay tên module nhạy cảm hay không.
- sourceRoot có chứa path tuyệt đối hoặc hostname nội bộ hay không.
- Có comment, endpoint nội bộ hoặc tên tính năng chưa phát hành không.
- Map có thuộc đúng release hay không.
- Map có thể truy cập không cần xác thực hay không.

Đừng chỉ tìm chuỗi password hoặc token rồi kết luận an toàn khi không thấy. Mã nguồn và metadata vẫn có thể tiết lộ logic, kiến trúc hoặc thông tin vận hành.

### 8.4 Kiểm tra cả nguồn phát hành

Một map có thể được phục vụ từ:

- Web server của ứng dụng.
- CDN.
- Object storage public bucket.
- Static hosting.
- Artifact registry được cấu hình public.
- Error monitoring service có quyền chia sẻ không phù hợp.

Kiểm tra nơi lưu trữ thực tế và các bản release cũ. Xóa map khỏi thư mục build mới không tự xóa bản đã cache hoặc bản còn nằm ở bucket khác.

## 9. Xử lý khi phát hiện map bị công khai ngoài ý muốn

Nếu map production chứa nội dung nội bộ và có thể truy cập công khai:

1. Xác nhận URL, release và phạm vi nội dung bị lộ.
2. Gỡ quyền truy cập public hoặc loại map khỏi vùng public.
3. Purge cache CDN và kiểm tra các replica hoặc object storage liên quan.
4. Kiểm tra log truy cập nếu hệ thống có lưu để xác định phạm vi truy cập.
5. Tìm secret hoặc credential vô tình nằm trong source; thu hồi và xoay vòng theo quy trình nếu phát hiện.
6. Sửa pipeline để map được lưu ở nơi riêng tư.
7. Build và deploy lại artifact theo chính sách mới.
8. Kiểm tra lại URL cũ, URL mới và các release cũ.
9. Ghi nhận nguyên nhân gốc và bổ sung kiểm tra tự động để ngăn tái diễn.

Không giả định rằng xóa comment sourceMappingURL là đủ. Người dùng có thể đã biết URL map, URL có thể được lưu trong log hoặc cache, và map có thể được truy cập độc lập.

## 10. Những lỗi triển khai thường gặp

### 10.1 Nghĩ hidden source map là private

Hidden thường chỉ bỏ comment tham chiếu trong bundle. Nếu tệp map vẫn được deploy vào public directory, nó vẫn có thể tải được. Phải kiểm tra quyền truy cập thực tế.

### 10.2 Nghĩ no-sources bảo đảm không lộ thông tin

No-sources bỏ nội dung source nhúng, nhưng sources và sourceRoot vẫn có thể tiết lộ cấu trúc dự án. Source gốc cũng có thể tải từ URL khác.

### 10.3 Chỉ xóa file .map khỏi thư mục local

CDN, object storage, release cũ hoặc cache có thể vẫn giữ map. Kiểm tra toàn bộ nơi phát hành và purge bản cũ theo quy trình.

### 10.4 Chỉ xóa comment sourceMappingURL

Comment không phải cơ chế xác thực. Nếu map có URL public đã biết hoặc dễ đoán, map vẫn có thể truy cập.

### 10.5 Để secret trong source rồi dựa vào minify

Mọi dữ liệu frontend gửi xuống browser đều có thể bị trích xuất. Secret cần được giữ ở server và không được bundle vào client.

### 10.6 Dùng map không khớp release

Map sai phiên bản làm DevTools hiển thị vị trí sai và có thể khiến quá trình xử lý sự cố đi theo hướng không chính xác. Gắn map với release hash hoặc identifier duy nhất.

### 10.7 Đưa map private vào thư mục public vì tiện deploy

Nếu toàn bộ thư mục build được đồng bộ lên CDN, map có thể bị phát hành ngoài ý muốn. Phân loại artifact và dùng allowlist cho bước deploy.

### 10.8 Dựa vào CORS để bảo vệ map

CORS không thay thế xác thực. Nếu URL map public, người dùng vẫn có thể tải bằng công cụ HTTP. Dùng kho lưu trữ riêng và cơ chế kiểm soát truy cập.

### 10.9 Không kiểm tra sourceRoot và đường dẫn nguồn

Map có thể chứa đường dẫn workstation, workspace hoặc hostname nội bộ. Kiểm tra metadata trước khi công khai.

### 10.10 Nghĩ source map tự tạo ra XSS

Source map là dữ liệu ánh xạ. Muốn kết luận XSS phải xác định đường dữ liệu không tin cậy đi tới sink có thể thực thi. Không đánh đồng việc lộ source với thực thi mã.

## 11. Quy trình review source map trước khi phát hành

Một quy trình review có thể áp dụng cho frontend web:

1. Xác định mục đích cần source map: debug tại browser, symbolication stack trace hay cả hai.
2. Chọn chế độ map theo từng môi trường.
3. Xác định map nào được public và map nào phải private.
4. Kiểm tra sourcesContent và metadata.
5. Xác nhận không có secret trong source hoặc bundle.
6. Gắn bundle và map với cùng release identifier.
7. Upload map private trước hoặc cùng thời điểm phát hành theo pipeline.
8. Loại map private khỏi thư mục public.
9. Kiểm tra comment sourceMappingURL trong bundle đã phát hành.
10. Kiểm tra URL .map đã biết bằng request không có credential.
11. Kiểm tra CDN, storage và artifact registry.
12. Kiểm tra cache và release cũ.
13. Thử giải mã một stack trace của release để xác nhận map private hoạt động.
14. Lưu kết quả kiểm tra cùng thông tin build.

## 12. Bài thực hành

Thực hiện các bài sau trong project local hoặc lab do bạn kiểm soát. Không cố ý phát hành source map chứa mã nội bộ lên một website public để thử nghiệm.

### Bài 1: Quan sát source map cơ bản

Tạo một ứng dụng JavaScript nhỏ có hai module. Build bundle với source map ở chế độ development. Mở trang bằng browser, bật DevTools và quan sát source gốc trong Sources.

Ghi lại URL bundle, URL map và vị trí comment sourceMappingURL.

### Bài 2: So sánh khi tắt source map

Tắt tùy chọn JavaScript source maps trong DevTools hoặc tạo build không có map. Tạo một lỗi có kiểm soát và so sánh stack trace giữa hai lần chạy.

Giải thích phần nào thay đổi và vì sao ứng dụng vẫn thực thi bundle.

### Bài 3: Đọc cấu trúc JSON map

Mở tệp .map trong môi trường local. Xác định version, file, sources, sourcesContent, sourceRoot, names và mappings.

Kiểm tra số phần tử trong sources và sourcesContent có tương ứng không. Tìm các đường dẫn có thể tiết lộ workspace hoặc cấu trúc repository.

### Bài 4: So sánh external và inline

Tạo hai bản build lab: một bản dùng external map và một bản dùng inline map. So sánh kích thước bundle, số request Network và khả năng truy cập nội dung map.

Không dùng inline map cho production chỉ vì thao tác cấu hình đơn giản.

### Bài 5: Kiểm tra hidden source map

Tạo build hidden source map bằng công cụ build đang dùng. Xác nhận bundle không có comment tham chiếu theo cấu hình đó và tệp map vẫn được tạo.

Sau đó thử deploy map vào thư mục public của máy chủ lab và kiểm tra URL. Kết quả cần cho thấy việc bỏ comment không ngăn truy cập nếu server vẫn phục vụ file.

### Bài 6: Kiểm tra no-sources source map

Tạo map không nhúng sourcesContent. Kiểm tra sources, sourceRoot và các URL source. Ghi nhận metadata còn lại và xác định source có thể được tải từ nơi khác hay không.

### Bài 7: Kiểm tra pipeline deploy

Tạo một thư mục public và một thư mục private cho artifact. Viết bước deploy chỉ copy bundle, CSS và tài nguyên được allowlist vào public; map được upload tới nơi lưu riêng.

Sau deploy, xác nhận request không credential tới URL map trả về kết quả không thể truy cập theo policy. Đồng thời xác nhận hệ thống debug vẫn giải mã stack trace bằng map private.

### Bài 8: Kiểm tra release mismatch

Dùng bundle từ build A và map từ build B trong lab. Quan sát lỗi ánh xạ hoặc vị trí không chính xác. Khôi phục map đúng release và ghi lại cách pipeline ngăn nhầm lẫn này.

## 13. Câu hỏi tự kiểm tra

**1. Source map giải quyết vấn đề gì?**

Source map ánh xạ vị trí trong mã generated về vị trí trong source ban đầu để DevTools hỗ trợ debug, breakpoint và stack trace dễ hiểu hơn.

**2. Browser thực thi bundle hay source được ánh xạ?**

Browser thực thi bundle đã tải. Source map hỗ trợ công cụ debug diễn giải vị trí trong mã generated.

**3. sourceMappingURL có tác dụng gì?**

Đây là chỉ thị trong bundle hoặc stylesheet cho biết vị trí source map tương ứng.

**4. sources và sourcesContent khác nhau thế nào?**

sources liệt kê định danh hoặc đường dẫn source; sourcesContent có thể chứa nội dung thực tế của từng source.

**5. Vì sao source map công khai có thể làm lộ mã nguồn?**

Map có thể nhúng nội dung source trong sourcesContent hoặc cung cấp đường dẫn để công cụ tải source. Người truy cập có thể đọc lại mã dễ dàng hơn.

**6. Hidden source map có tự bảo vệ tệp map không?**

Không. Hidden thường bỏ comment tham chiếu trong bundle. Nếu map vẫn nằm ở URL public, người dùng vẫn có thể tải.

**7. No-sources source map có loại bỏ mọi thông tin nhạy cảm không?**

Không. Tên tệp, sourceRoot, đường dẫn và metadata ánh xạ vẫn có thể tiết lộ cấu trúc dự án; source cũng có thể truy cập từ nơi khác.

**8. Có thể dùng CORS để giữ bí mật một map public không?**

Không. CORS không phải cơ chế xác thực hoặc phân quyền cho tài nguyên public.

**9. Vì sao bundle và map phải cùng release?**

Nếu không khớp, DevTools có thể ánh xạ dòng và vị trí sang source khác, khiến việc debug và xử lý sự cố sai lệch.

**10. Nếu secret bị phát hiện trong sourcesContent, cần làm gì?**

Xem secret là có khả năng đã lộ, thu hồi hoặc xoay vòng theo quy trình, gỡ map khỏi nơi public, purge cache và sửa pipeline để ngăn tái diễn.

## 14. Checklist bảo mật source map

- [ ] Đã xác định mục đích tạo source map cho từng môi trường.
- [ ] Development có map phù hợp để debug.
- [ ] Production có chính sách rõ ràng về map public và private.
- [ ] Bundle và map được tạo từ cùng commit và release.
- [ ] Map private được upload tới kho artifact hoặc dịch vụ theo dõi lỗi có kiểm soát truy cập.
- [ ] Map private không nằm trong thư mục public được deploy.
- [ ] Đã kiểm tra comment sourceMappingURL trong bundle production.
- [ ] Đã kiểm tra các URL map có thể truy cập mà không cần credential.
- [ ] Đã kiểm tra cả CDN, object storage và artifact registry.
- [ ] Đã kiểm tra sourcesContent.
- [ ] Đã kiểm tra sources và sourceRoot để tìm đường dẫn nội bộ.
- [ ] Không có secret trong source hoặc bundle frontend.
- [ ] Đã hiểu hidden không đồng nghĩa private.
- [ ] Đã hiểu no-sources vẫn có thể tiết lộ metadata.
- [ ] Không dựa vào CORS, CSP, minification hoặc tên file để bảo vệ map.
- [ ] Đã có quy trình purge map cũ và cache khi phát hiện phát hành nhầm.
- [ ] Đã xác nhận stack trace có thể được giải mã bằng map đúng release.
- [ ] Đã lưu bằng chứng kiểm tra cho lần phát hành.

## Ghi nhớ

Source map giúp DevTools ánh xạ mã đã build về mã nguồn ban đầu để debug. Browser vẫn thực thi bundle; map là dữ liệu hỗ trợ công cụ phát triển. Source map có thể tiết lộ source, tên module và đường dẫn nội bộ, đặc biệt khi sourcesContent được nhúng. Hidden chỉ bỏ chỉ thị tham chiếu, còn no-sources chỉ bỏ nội dung source nhúng; cả hai đều không thay thế kiểm soát truy cập. Với production, hãy gắn map đúng release, lưu map cần thiết ở nơi riêng tư, loại chúng khỏi artifact public và kiểm tra URL thực tế sau deploy. Không bao giờ đặt secret trong mã frontend.

## Tài liệu tham khảo

- [ECMA-426: Source Map Format](https://tc39.es/ecma426/)
- [MDN: Source maps](https://developer.mozilla.org/en-US/docs/Glossary/Source_map)
- [Chrome DevTools: Understand the code structure with the Sources panel](https://developer.chrome.com/docs/devtools/sources/)
- [webpack: devtool configuration](https://webpack.js.org/configuration/devtool/)
- [Vite: Build options](https://vite.dev/config/build-options.html)
- [OWASP: Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP: Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
