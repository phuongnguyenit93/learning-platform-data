# Console log

Console log là cách ghi lại thông tin trong lúc JavaScript chạy để quan sát dữ liệu, luồng xử lý và lỗi ngay trong trình duyệt. Khi làm việc với ứng dụng web, DevTools Console giúp trả lời những câu hỏi cụ thể: hàm có được gọi hay không, nhánh điều kiện nào được thực hiện, máy chủ trả về trạng thái gì, hoặc giá trị đã thay đổi ở bước nào.

Trong phạm vi bảo mật ứng dụng web, log còn giúp kiểm tra các giả định về dữ liệu và luồng xử lý. Tuy nhiên, mọi thông tin được ghi ra Console đều có thể bị người đang kiểm tra trang nhìn thấy. Vì vậy, cần chọn dữ liệu có chủ đích và tránh đưa bí mật hoặc dữ liệu cá nhân vào log.

## Mục tiêu

Sau bài học, bạn có thể:

- Mở DevTools Console, chọn đúng execution context và lọc thông điệp theo mức độ.
- Dùng các phương thức `console` để ghi thông tin, cảnh báo, lỗi, bảng dữ liệu, nhóm log và thời gian thực thi.
- Đọc vị trí phát sinh log, stack trace và hiểu giới hạn khi quan sát object.
- Thiết kế log phục vụ gỡ lỗi mà không làm lộ token, cookie, thông tin xác thực hoặc dữ liệu người dùng.
- Phân biệt log chẩn đoán ở trình duyệt với kiểm soát bảo mật và nhật ký kiểm toán ở phía máy chủ.

## Console log hoạt động như thế nào?

`console` là một đối tượng được trình duyệt cung cấp cho mã JavaScript. Các phương thức như `console.log()`, `console.warn()` và `console.error()` gửi thông điệp tới công cụ Console của môi trường đang chạy. DevTools nhận thông điệp, hiển thị mức độ, nội dung và thường kèm liên kết tới vị trí gọi phương thức trong mã nguồn.

Ví dụ đơn giản:

```js
const account = { id: 42, role: "viewer" };

console.log("Đã tải cấu hình tài khoản:", account);
console.info("Ứng dụng đã sẵn sàng");
console.warn("Thiếu cấu hình tùy chọn");
```

Các lệnh trên không thay đổi luồng xử lý của ứng dụng. Chúng ghi thông tin để người phát triển quan sát. `console.error()` cũng không tự xử lý ngoại lệ hoặc khôi phục ứng dụng; muốn xử lý lỗi, chương trình vẫn cần `try...catch`, kiểm tra kết quả hoặc cơ chế phù hợp khác.

Console trong DevTools còn có thể nhận lệnh JavaScript do người dùng nhập trực tiếp. Đây là hai hoạt động khác nhau: mã ứng dụng gọi Console API để ghi log, còn lệnh nhập trong Console được thực thi trong execution context đã chọn. Chỉ chạy lệnh mà bạn hiểu rõ nguồn gốc và tác động của nó.

## Mở Console và xác định đúng ngữ cảnh

Trong các trình duyệt phổ biến, có thể mở DevTools bằng menu công cụ dành cho nhà phát triển hoặc phím tắt của trình duyệt. Sau đó chọn tab **Console**. Tên menu, phím tắt và cách bố trí có thể khác nhau giữa Chrome, Edge, Firefox và Safari.

Trước khi đọc log, hãy kiểm tra:

1. **Trang hoặc frame đang được chọn:** một trang có thể chứa iframe với origin khác. Console có thể cho phép chọn execution context tương ứng. Log của frame con không nhất thiết xuất hiện cùng ngữ cảnh với frame chính.
2. **Worker đang chạy:** thông điệp từ Web Worker hoặc Service Worker có thể nằm trong Console riêng hoặc khu vực DevTools tương ứng. Hãy mở đúng worker khi cần chẩn đoán.
3. **Mức độ thông điệp:** bật các mức `Verbose`, `Info`, `Warnings` và `Errors` phù hợp. Một bộ lọc đang tắt có thể khiến bạn tưởng rằng mã không ghi log.
4. **Bộ lọc văn bản và nguồn:** bỏ bộ lọc cũ, kiểm tra bộ lọc theo URL hoặc loại thông điệp nếu kết quả đang thiếu.
5. **Preserve log:** bật tùy chọn giữ log khi cần theo dõi điều hướng hoặc tải lại trang. Nếu tắt, Console có thể được làm sạch khi trang chuyển trạng thái.

Một dòng log thường có biểu tượng hoặc kiểu trình bày thể hiện mức độ, nội dung thông điệp và liên kết tới tệp cùng dòng mã phát sinh. Nhấp vào liên kết nguồn để mở vị trí tương ứng trong Sources. Khi log nằm trong callback bất đồng bộ, hãy đọc thêm stack trace và chuỗi lời gọi liên quan thay vì chỉ dựa vào tên hàm.

## Các phương thức Console thường dùng

| Phương thức | Mục đích | Cách sử dụng |
|---|---|---|
| `console.log()` | Ghi thông tin thông thường | Giá trị biến, trạng thái và kết quả trung gian |
| `console.info()` | Ghi thông tin mang tính thông báo | Mốc khởi tạo hoặc một bước đã hoàn tất |
| `console.debug()` | Ghi thông tin chi tiết phục vụ gỡ lỗi | Giá trị nội bộ chỉ cần khi điều tra sâu; có thể bị bộ lọc ẩn |
| `console.warn()` | Ghi cảnh báo | Cấu hình thiếu, trạng thái bất thường nhưng chưa làm luồng xử lý thất bại |
| `console.error()` | Ghi lỗi | Một thao tác thất bại hoặc ngoại lệ cần được điều tra |
| `console.table()` | Trình bày dữ liệu dạng bảng | Mảng object hoặc tập bản ghi có cùng cấu trúc |
| `console.dir()` | Xem thuộc tính của object | Kiểm tra object hoặc node theo dạng cây thuộc tính |
| `console.group()` | Mở một nhóm log | Gom các thông điệp thuộc cùng một thao tác |
| `console.groupCollapsed()` | Mở nhóm ở trạng thái thu gọn | Giữ Console gọn khi có nhiều bước chẩn đoán |
| `console.groupEnd()` | Đóng nhóm hiện tại | Kết thúc nhóm đã mở |
| `console.time()` | Bắt đầu đo thời gian theo nhãn | Đo một đoạn xử lý |
| `console.timeLog()` | Ghi thời gian đã trôi qua mà chưa kết thúc phép đo | Quan sát một mốc trung gian |
| `console.timeEnd()` | Ghi thời gian và kết thúc phép đo | Hoàn tất phép đo đã bắt đầu |
| `console.count()` | Tăng và hiển thị bộ đếm theo nhãn | Đếm số lần một nhánh hoặc callback được gọi |
| `console.countReset()` | Đặt lại bộ đếm theo nhãn | Bắt đầu một lượt đếm mới |
| `console.assert()` | Ghi thông điệp khi điều kiện sai | Kiểm tra một giả định trong lúc phát triển |
| `console.trace()` | Ghi stack trace tại vị trí gọi | Tìm đường đi dẫn tới một hàm |
| `console.clear()` | Yêu cầu làm sạch Console | Dọn thông điệp cũ khi bắt đầu một lượt kiểm tra |

Giao diện và cách trình bày có thể khác nhau giữa các trình duyệt. Một số mức log có thể bị ẩn theo bộ lọc. Vì vậy, khi không thấy thông điệp, hãy kiểm tra bộ lọc và execution context trước khi kết luận rằng câu lệnh không chạy.

### Ghi thông điệp và nhiều giá trị

Các phương thức log nhận nhiều đối số:

```js
const status = 200;
const durationMs = 86;

console.log("Phản hồi API:", status, "thời gian:", durationMs, "ms");
console.warn("Yêu cầu gần chạm ngưỡng thời gian", durationMs);
```

Đặt nhãn dễ tìm ở đầu thông điệp giúp lọc log của một chức năng:

```js
console.info("[settings] Bắt đầu tải cấu hình");
console.info("[settings] Đã nhận phản hồi");
```

Nhãn nên ngắn, ổn định và mô tả chức năng. Tránh dùng dữ liệu nhạy cảm làm nhãn hoặc nội dung log.

### Định dạng thông điệp

Console hỗ trợ một số ký hiệu định dạng trong chuỗi đầu tiên. Khả năng và cách hiển thị có thể khác nhau đôi chút giữa trình duyệt.

```js
const endpoint = "/api/settings";
const durationMs = 86;

console.log("Gọi %s mất %d ms", endpoint, durationMs);
console.log("Giá trị thập phân: %f", 12.5);
```

Một số ký hiệu thường gặp:

- `%s`: chuyển đối số thành chuỗi.
- `%d` hoặc `%i`: hiển thị giá trị số nguyên.
- `%f`: hiển thị giá trị số thực.
- `%o` và `%O`: hiển thị object theo cách trình duyệt hỗ trợ.
- `%c`: áp dụng CSS cho phần văn bản tiếp theo trong thông điệp.

Ví dụ dùng `%c` để làm nổi bật nhãn:

```js
console.log(
  "%cSECURITY%c Kiểm tra cấu hình hoàn tất",
  "color: #b45309; font-weight: bold",
  "color: inherit"
);
```

Định dạng chỉ giúp đọc log thuận tiện hơn. Không dùng màu sắc hoặc kiểu chữ để thay thế mức độ `warn` hay `error`, vì người đọc có thể lọc thông điệp theo mức độ.

### Xem dữ liệu có cấu trúc

`console.table()` hữu ích khi cần so sánh nhiều bản ghi có cùng các trường:

```js
const checks = [
  { name: "content-type", passed: true },
  { name: "https-only", passed: true },
  { name: "session-cookie", passed: false }
];

console.table(checks);
```

Đối số thứ hai có thể dùng để giới hạn các cột cần hiển thị:

```js
console.table(checks, ["name", "passed"]);
```

Chỉ đưa vào bảng những trường cần thiết. Không ghi nguyên bản ghi người dùng, payload xác thực hoặc toàn bộ phản hồi API chỉ để tiện quan sát.

`console.dir()` trình bày thuộc tính của một object theo dạng cây, phù hợp khi cần xem cấu trúc lồng nhau:

```js
const result = {
  ok: true,
  metadata: { source: "cache", ageSeconds: 12 }
};

console.dir(result);
```

Khi kiểm tra phần tử DOM, `console.log(element)` và `console.dir(element)` có thể trình bày phần tử theo cách khác nhau. Hãy chọn cách hiển thị phù hợp với điều cần kiểm tra, đồng thời nhớ rằng nội dung text hoặc thuộc tính của phần tử có thể chứa dữ liệu nhạy cảm.

### Nhóm log và đo thời gian

Nhóm log giúp gom thông tin của cùng một thao tác:

```js
console.groupCollapsed("[settings] Tải cấu hình");
console.info("Bắt đầu yêu cầu");
console.log("HTTP status:", 200);
console.info("Đã phân tích phản hồi");
console.groupEnd();
```

Luôn đóng nhóm bằng `console.groupEnd()` ở vị trí phù hợp. Nếu có nhiều nhánh hoặc ngoại lệ, dùng `try...finally` để tránh để nhóm mở ngoài ý muốn.

Các phương thức `time`, `timeLog` và `timeEnd` dùng chung một nhãn:

```js
console.time("settings-load");

// Thực hiện bước cần đo.
await loadSettings();

console.timeLog("settings-load", "Đã tải xong dữ liệu");
console.timeEnd("settings-load");
```

Trong ví dụ thực tế, đặt `timeEnd()` trong `finally` để phép đo vẫn được kết thúc khi thao tác thất bại:

```js
console.time("settings-load");
try {
  await loadSettings();
} catch (error) {
  console.error("Không thể tải cấu hình", error);
  throw error;
} finally {
  console.timeEnd("settings-load");
}
```

Đo thời gian bằng Console hữu ích cho chẩn đoán nhanh. Kết quả phụ thuộc thiết bị, trạng thái mạng, bộ nhớ đệm và các tác vụ khác đang chạy; đây không phải phép đo hiệu năng có kiểm soát để so sánh giữa các môi trường.

### Đếm lời gọi, kiểm tra giả định và truy vết

`console.count()` giúp phát hiện một callback bị gọi nhiều lần:

```js
function onSearchInput() {
  console.count("search-input");
  // Xử lý nội dung tìm kiếm.
}
```

Đặt lại bộ đếm khi cần bắt đầu lượt quan sát mới:

```js
console.countReset("search-input");
```

`console.assert()` ghi thông điệp khi điều kiện là sai:

```js
console.assert(items.length <= 100, "Số lượng mục vượt ngưỡng dự kiến");
```

`console.assert()` không ném exception và không dừng chương trình. Nó chỉ giúp phát hiện giả định bị vi phạm trong lúc quan sát. Mọi kiểm tra đầu vào, phân quyền hoặc giới hạn tài nguyên cần thiết vẫn phải được thực thi bằng logic của ứng dụng và phía máy chủ.

`console.trace()` hiển thị stack trace tại nơi gọi:

```js
function updateView() {
  console.trace("Đường đi gọi updateView");
}
```

Stack trace giúp lần ngược các hàm dẫn tới một vị trí. Với tác vụ bất đồng bộ, stack có thể không thể hiện toàn bộ lịch sử trước đó; hãy kết hợp log có nhãn, breakpoint và thông tin trong các tab Network hoặc Sources.

## Đọc object và thời điểm ghi log

Khi ghi object, một số DevTools giữ tham chiếu tới object và chỉ đọc thuộc tính khi người dùng mở rộng dòng log. Nếu object tiếp tục thay đổi sau câu lệnh `console.log()`, nội dung nhìn thấy khi mở rộng có thể phản ánh trạng thái mới hơn thời điểm ghi log.

```js
const state = { phase: "pending" };
console.log("state:", state);

state.phase = "complete";
```

Tùy trình duyệt và cách hiển thị, khi mở rộng object, bạn có thể thấy `phase` là `complete`. Điều đó không chứng minh rằng giá trị đã là `complete` tại thời điểm gọi `console.log()`.

Nếu cần lưu lại một ảnh chụp đơn giản của trạng thái, có thể tạo object mới:

```js
console.log("state snapshot:", { ...state });
```

Đây là bản sao nông: các object lồng bên trong vẫn có thể được chia sẻ tham chiếu. Với dữ liệu có thể sao chép bằng structured clone, `structuredClone()` tạo bản sao sâu:

```js
console.log("state snapshot:", structuredClone(state));
```

`structuredClone()` không áp dụng được cho mọi giá trị, chẳng hạn một số hàm hoặc node DOM. Không chuyển toàn bộ object sang JSON chỉ để tạo log nếu object có vòng tham chiếu, `BigInt`, kiểu dữ liệu đặc biệt hoặc dữ liệu nhạy cảm. Hãy chọn một tập trường nhỏ và an toàn để ghi.

## Quy trình gỡ lỗi bằng Console

Một quy trình có mục tiêu giúp giảm số lượng log và rút ngắn thời gian tìm nguyên nhân:

1. **Mô tả hiện tượng:** ghi rõ thao tác gây lỗi, trạng thái mong đợi và trạng thái thực tế.
2. **Tái hiện lỗi:** mở đúng trang, frame hoặc worker; bật Preserve log nếu lỗi xảy ra khi điều hướng.
3. **Đặt log tại ranh giới xử lý:** ghi một mốc khi nhận sự kiện, trước khi gửi yêu cầu, sau khi nhận phản hồi và khi cập nhật trạng thái.
4. **Ghi giá trị tối thiểu:** ưu tiên trạng thái, số lượng, kiểu dữ liệu, mã HTTP hoặc boolean cho biết một điều kiện có đúng hay không.
5. **Đọc nguồn và stack trace:** nhấp vào vị trí nguồn, lần theo hàm gọi và kiểm tra xem log thuộc lần chạy nào.
6. **Đối chiếu công cụ khác:** dùng Network để xem request/response, Sources để đặt breakpoint và Application để kiểm tra storage hoặc cookie khi có quyền và nhu cầu phù hợp.
7. **Xóa log tạm:** sau khi tìm được nguyên nhân, bỏ các câu lệnh không còn cần thiết hoặc chuyển sang cơ chế ghi log được quản lý phù hợp với môi trường.

Ví dụ sau ghi lại quá trình tải cấu hình mà không in nội dung cấu hình ra Console:

```js
async function loadSettings() {
  console.groupCollapsed("[settings] load");
  console.time("settings-load");

  try {
    const response = await fetch("/api/settings");
    console.info("HTTP status:", response.status);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const settings = await response.json();
    console.table([
      { field: "theme", present: typeof settings.theme === "string" },
      { field: "language", present: typeof settings.language === "string" }
    ]);
  } catch (error) {
    console.error("Không thể tải cấu hình", error);
    throw error;
  } finally {
    console.timeEnd("settings-load");
    console.groupEnd();
  }
}
```

Trong ứng dụng thật, chỉ ghi các thuộc tính đã được xác định là an toàn. Ngay cả tên trường, URL, thông báo lỗi hoặc stack trace cũng có thể để lộ thông tin về hệ thống nếu chứa đường dẫn nội bộ, định danh hoặc dữ liệu do người dùng cung cấp.

## Console log và an toàn ứng dụng

Console là công cụ chẩn đoán ở phía trình duyệt. Nội dung log có thể được nhìn thấy bởi người đang sử dụng DevTools, người xem phiên làm việc được chia sẻ hoặc hệ thống thu thập log nếu ứng dụng chủ động chuyển thông tin ra ngoài. Hãy xem log như một bề mặt có thể làm lộ dữ liệu.

### Không ghi bí mật hoặc dữ liệu cá nhân

Không ghi các giá trị sau vào Console:

- Mật khẩu, mã xác thực một lần, access token, refresh token và API key.
- Giá trị cookie phiên, header `Authorization`, thông tin xác thực hoặc dữ liệu dùng để khôi phục phiên.
- Toàn bộ thông tin cá nhân, nội dung biểu mẫu, dữ liệu thanh toán hoặc phản hồi API có chứa dữ liệu riêng tư.
- URL đầy đủ nếu query string hoặc fragment chứa mã truy cập, định danh hoặc dữ liệu nhạy cảm.

Thay vì ghi nguyên giá trị, hãy ghi dấu hiệu tối thiểu cần cho việc chẩn đoán:

```js
// Không ghi token hoặc nội dung hồ sơ.
console.info("[auth] token present:", Boolean(accessToken));
console.info("[profile] response received:", response.ok);
```

Boolean vẫn có thể tiết lộ một phần trạng thái xác thực. Chỉ ghi thông tin này khi nó thực sự cần thiết và phù hợp với chính sách dữ liệu của ứng dụng.

### Không dùng log làm cơ chế bảo mật

Log trong trình duyệt không phải bằng chứng kiểm toán đáng tin cậy. Người dùng có thể sửa mã phía client, tắt hoặc xóa log, thay đổi dữ liệu trong bộ nhớ và gọi trực tiếp API. Vì vậy:

- Phân quyền và xác thực phải được kiểm tra ở phía máy chủ cho từng thao tác cần bảo vệ.
- Không dựa vào `console.assert()`, `console.error()` hoặc một thông điệp log để chặn hành vi trái phép.
- Không coi việc không thấy lỗi trong Console là bằng chứng rằng request an toàn hoặc máy chủ đã xử lý đúng.
- Sự kiện kiểm toán quan trọng phải được ghi ở hệ thống phía máy chủ, có kiểm soát quyền truy cập, tính toàn vẹn và thời hạn lưu giữ phù hợp.

### Quản lý log trong môi trường production

Log tạm hữu ích trong phát triển nhưng có thể tạo thêm chi phí, làm lộ dữ liệu và gây nhiễu khi phát hành. Trước khi triển khai:

- Xóa các log kiểm tra không còn cần thiết; không giả định rằng mọi công cụ build đều tự loại bỏ `console.log()`.
- Nếu cần ghi lỗi phía client, dùng cơ chế telemetry đã được thiết kế với danh sách trường cho phép, lọc dữ liệu nhạy cảm và quyền truy cập rõ ràng.
- Không gửi toàn bộ object lỗi hoặc trạng thái ứng dụng lên dịch vụ bên ngoài nếu chưa kiểm tra các trường có thể chứa dữ liệu người dùng.
- Kiểm tra source map, URL và thông điệp lỗi để tránh công khai thông tin nội bộ không cần thiết.

Console có thể hiển thị chuỗi do người dùng hoặc máy chủ cung cấp. Hãy xem nội dung đó là dữ liệu không đáng tin cậy khi phân tích. Không sao chép một đoạn lệnh từ log hoặc từ người lạ rồi dán vào Console để chạy nếu chưa hiểu rõ mã sẽ thực hiện gì.

## Lỗi thường gặp khi đọc Console

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không thấy log | Sai execution context, mức log bị lọc hoặc mã chưa chạy | Chọn đúng frame/worker, bật mức phù hợp và đặt breakpoint |
| Log biến mất sau điều hướng | Preserve log đang tắt | Bật Preserve log rồi tái hiện thao tác |
| Thứ tự log khó hiểu | Callback bất đồng bộ hoặc nhiều tác vụ chạy xen kẽ | Thêm nhãn và mã tương quan không nhạy cảm; đối chiếu Network và stack trace |
| Object hiển thị giá trị mới | DevTools có thể đọc object khi mở rộng | Ghi snapshot có chọn lọc tại thời điểm cần quan sát |
| Cảnh báo lặp nhiều lần | Callback hoặc effect chạy nhiều lần, hoặc log nằm trong vòng lặp | Dùng `console.count()` và kiểm tra điều kiện gọi |
| Thông điệp lỗi không chỉ ra nguyên nhân | Log thiếu ngữ cảnh hoặc lỗi được bắt ở nơi khác | Ghi tên thao tác, mã trạng thái an toàn và stack trace phù hợp |

Không nên thêm log ở mọi dòng mã. Hãy bắt đầu tại ranh giới giữa các bước xử lý, sau đó thu hẹp phạm vi theo bằng chứng thu được.

## Thực hành

Tạo một trang thử nghiệm hoặc mở một ứng dụng mẫu mà bạn có quyền kiểm tra. Chạy đoạn mã sau trong mã thử nghiệm:

```js
const requests = [
  { name: "settings", status: 200, durationMs: 48 },
  { name: "profile", status: 403, durationMs: 31 },
  { name: "preferences", status: 200, durationMs: 72 }
];

console.group("[diagnostics] requests");
console.table(requests);

for (const request of requests) {
  console.count(`status-${request.status}`);

  if (request.status >= 400) {
    console.warn("Request cần kiểm tra:", request.name, request.status);
  }
}

console.groupEnd();
```

Quan sát kết quả và trả lời:

1. `console.table()` giúp so sánh ba request như thế nào?
2. Bộ đếm nào tăng khi request có trạng thái `200`, và bộ đếm nào tăng khi trạng thái là `403`?
3. Vì sao trạng thái `403` nên được điều tra ở Network và phía máy chủ thay vì chỉ dựa vào dòng cảnh báo?
4. Nếu thay `request.name` bằng email hoặc token của người dùng, rủi ro nào xuất hiện?

Tiếp theo, thử thêm `console.time()` và `console.timeEnd()` quanh một thao tác bất đồng bộ. Đặt phép đo trong `try...finally`, sau đó gây lỗi có kiểm soát để xác nhận phép đo vẫn được kết thúc. Không dùng tài khoản thật hoặc dữ liệu nhạy cảm cho bài thực hành.

## Ghi nhớ

- Dùng `log`, `info`, `debug`, `warn` và `error` để thể hiện đúng mục đích của thông điệp.
- Dùng `table`, `group`, `time`, `count`, `assert` và `trace` khi chúng giúp câu hỏi gỡ lỗi trở nên rõ ràng.
- Kiểm tra frame, worker, mức log, bộ lọc và Preserve log trước khi kết luận rằng thông điệp bị mất.
- Object trong Console có thể được hiển thị theo trạng thái tại thời điểm mở rộng; tạo snapshot có chọn lọc khi cần.
- Không ghi token, cookie, mật khẩu, dữ liệu cá nhân hoặc toàn bộ payload vào log.
- Console hỗ trợ chẩn đoán phía client; xác thực, phân quyền và kiểm toán vẫn cần được bảo đảm ở phía máy chủ.
