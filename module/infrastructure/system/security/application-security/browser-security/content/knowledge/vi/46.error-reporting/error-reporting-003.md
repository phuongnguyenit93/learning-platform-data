# Unhandled exception: bắt lỗi không được xử lý và báo cáo an toàn trong trình duyệt

> **Chương:** Error và report  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

Một **unhandled exception** là lỗi được ném ra nhưng không có khối xử lý phù hợp trong luồng thực thi hiện tại. Trong JavaScript trình duyệt, lỗi đồng bộ không được bắt thường tạo ra sự kiện global **error**. Promise bị reject mà không có rejection handler kịp thời có thể tạo sự kiện **unhandledrejection**. Hai sự kiện này phản ánh hai đường lỗi khác nhau và cần được quan sát riêng.

Bắt được lỗi ở global scope không có nghĩa ứng dụng đã phục hồi. Global handler chỉ là lớp quan sát cuối cùng để ghi nhận lỗi, bổ sung ngữ cảnh và gửi báo cáo. Việc khôi phục giao diện, hoàn tác thao tác, thông báo cho người dùng hoặc retry phải được thiết kế tại nơi ứng dụng hiểu nghiệp vụ. Nếu dùng global handler để âm thầm bỏ qua lỗi, ứng dụng có thể tiếp tục với trạng thái không nhất quán.

Bài này đi từ cách exception lan truyền qua call stack, callback và Promise đến các sự kiện error, unhandledrejection, rejectionhandled, lỗi tài nguyên và lỗi trong Worker. Phần cuối xây dựng một pipeline báo cáo có giới hạn dữ liệu và lab Node.js để quan sát từng trường hợp.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt exception đồng bộ, Promise rejection và lỗi tải tài nguyên.
2. Giải thích vì sao try/catch chỉ bắt lỗi trong phạm vi luồng thực thi mà nó bao quanh.
3. Xử lý lỗi trong async/await, Promise chain, event listener và timer.
4. Dùng window error event để quan sát exception không được bắt.
5. Dùng unhandledrejection và rejectionhandled để theo dõi Promise rejection.
6. Phân biệt ErrorEvent với Event phát sinh khi tài nguyên không tải được.
7. Hiểu giới hạn quan sát lỗi từ script cross-origin.
8. Thu thập lỗi từ Web Worker qua error, messageerror và message có schema.
9. Chuẩn hóa Error và rejection reason mà không giả định mọi reason đều là Error.
10. Gửi báo cáo có giới hạn kích thước, tần suất và dữ liệu nhạy cảm.
11. Phân biệt lỗi JavaScript với CSP violation và lỗi nghiệp vụ.
12. Kiểm thử đường lỗi bằng DevTools và lab trên localhost.

## 1. Exception và unhandled exception

### 1.1 Exception là gì?

JavaScript tạo exception khi một thao tác ném giá trị bằng throw hoặc khi runtime gặp lỗi như truy cập thuộc tính không hợp lệ, gọi hàm không tồn tại, lỗi cú pháp lúc parse hoặc lỗi trong một API.

~~~js
function parseSettings(text) {
  const settings = JSON.parse(text);

  if (settings === null || typeof settings !== 'object') {
    throw new TypeError('Settings phải là object');
  }

  return settings;
}
~~~

Exception là cơ chế điều khiển luồng. Khi một exception được ném, JavaScript dừng phần còn lại của nhánh hiện tại và tìm handler gần nhất trong call stack. Nếu tìm thấy catch, luồng chuyển sang catch. Nếu không có handler phù hợp, exception trở thành lỗi không được xử lý trong execution context đó.

### 1.2 Unhandled không đồng nghĩa với ứng dụng đã dừng

Một uncaught exception thường kết thúc lần thực thi hiện tại của script hoặc callback. Nó không nhất thiết đóng tab hoặc dừng toàn bộ ứng dụng. Những task, event listener và callback khác vẫn có thể tiếp tục chạy.

Điều này tạo ra một rủi ro: ứng dụng có thể mất một bước cập nhật nhưng tiếp tục nhận thao tác mới. Ví dụ, giao diện đã khóa nút gửi nhưng exception xảy ra trước khi mở khóa. Người dùng thấy ứng dụng bị treo dù trang vẫn hoạt động.

Khi báo cáo lỗi, cần ghi nhận thao tác và component liên quan ở mức đủ để điều tra. Phục hồi phải do code nghiệp vụ thực hiện tại nơi có thể biết trạng thái nào đã thay đổi.

### 1.3 Ba nhóm lỗi thường gặp

| Nhóm | Ví dụ | Cách quan sát chính |
|---|---|---|
| Exception đồng bộ không được bắt | throw trong function, event callback hoặc timer callback | error event trên global |
| Promise rejection không được xử lý | Promise.reject(), lỗi trong async function | unhandledrejection |
| Lỗi tải tài nguyên | script, image, stylesheet hoặc font không tải được | error event trên element, thường cần capture phase |

Một request fetch trả HTTP 404 không tự tạo uncaught exception. Promise fetch vẫn resolve với Response; code phải kiểm tra status và chủ động throw nếu đó là lỗi đối với nghiệp vụ.

### 1.4 Luôn ném Error object

JavaScript cho phép throw mọi giá trị:

~~~js
throw 'Không thể tải dữ liệu';
throw 42;
throw { code: 'FAILED' };
~~~

Cách này làm việc xử lý và báo cáo khó nhất quán. Hãy ném Error hoặc subclass của Error:

~~~js
throw new Error('Không thể tải dữ liệu');
~~~

Error object cung cấp name, message và thường có stack. Stack format phụ thuộc engine và không được chuẩn hóa để parse bằng regex. Không dùng stack như một định danh ổn định giữa các browser.

## 2. Exception lan truyền qua call stack

### 2.1 try/catch bắt lỗi trong luồng đồng bộ được bao quanh

~~~js
function loadConfiguration() {
  throw new Error('Configuration file is invalid');
}

try {
  loadConfiguration();
  console.log('Dòng này không chạy');
} catch (error) {
  console.error('Không tải được cấu hình:', error.message);
}
~~~

Khi exception phát sinh trong lời gọi đồng bộ bên trong try, nó lan ngược qua các stack frame cho đến catch phù hợp. Sau khi catch xử lý xong, chương trình tiếp tục sau khối try/catch.

### 2.2 try/catch không bắt lỗi xảy ra ở task khác

Ví dụ sau không bắt được lỗi trong timer:

~~~js
try {
  setTimeout(() => {
    throw new Error('Lỗi xảy ra sau đó');
  }, 0);
} catch (error) {
  console.error('Không bắt được lỗi timer này');
}
~~~

Khi setTimeout được gọi, callback chỉ được đăng ký. Khối try kết thúc trước khi callback chạy. Khi callback chạy ở một task khác, call stack ban đầu đã không còn.

Cách xử lý đúng là đặt try/catch bên trong callback:

~~~js
setTimeout(() => {
  try {
    runScheduledTask();
  } catch (error) {
    reportLocalFailure(error);
  }
}, 0);
~~~

Nếu callback là async, cần bắt cả rejection của Promise mà async function trả về.

### 2.3 Event listener cũng tạo ranh giới callback

~~~js
button.addEventListener('click', () => {
  throw new Error('Lỗi trong click handler');
});
~~~

try/catch ở nơi đăng ký listener không bao quanh lúc listener được gọi:

~~~js
try {
  button.addEventListener('click', () => {
    throw new Error('Không được catch ở đây');
  });
} catch (error) {
  // Không bắt exception phát sinh khi click sau này.
}
~~~

Đặt catch trong callback nếu cần phục hồi cục bộ. Nếu lỗi không được xử lý, browser có thể phát global error event cho exception đồng bộ đó.

### 2.4 Không có một try/catch bao quanh toàn bộ vòng đời trang

Một ứng dụng web có nhiều execution boundary: script, timer, event listener, Promise microtask, Worker và Service Worker. Mỗi boundary cần xử lý lỗi ở nơi thích hợp.

Global handler giúp quan sát những lỗi lọt qua, nhưng không thể đưa call stack đã kết thúc trở lại trạng thái trước lỗi. Đừng thiết kế ứng dụng dựa vào giả định rằng một catch ở đầu file sẽ bắt mọi lỗi về sau.

## 3. Promise rejection và async/await

### 3.1 throw bên trong Promise callback biến thành rejection

~~~js
Promise.resolve()
  .then(() => {
    throw new Error('Lỗi trong then callback');
  })
  .catch(error => {
    console.error('Đã xử lý rejection:', error.message);
  });
~~~

Promise chain chuyển exception trong callback thành rejection của Promise tiếp theo. catch có thể xử lý rejection đó. Giá trị mà catch trả về sẽ quyết định trạng thái của Promise mới.

### 3.2 Bỏ quên catch tạo unhandled rejection

~~~js
function loadData() {
  return fetch('/api/data');
}

loadData().then(response => {
  if (!response.ok) {
    throw new Error('HTTP ' + response.status);
  }

  return response.json();
});
~~~

Đoạn code không lưu Promise cuối cùng và không gắn rejection handler. Nếu fetch reject, response.json() reject hoặc callback throw, Promise cuối cùng có thể trở thành unhandled rejection.

Cách xử lý:

~~~js
loadData()
  .then(response => {
    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }

    return response.json();
  })
  .catch(error => {
    showLoadFailure();
    reportLocalFailure(error);
  });
~~~

catch nên đặt ở ranh giới nơi ứng dụng biết phải hiển thị trạng thái nào. Không thêm một catch rỗng chỉ để làm biến mất cảnh báo.

### 3.3 async function luôn trả về Promise

~~~js
async function refreshProfile() {
  throw new Error('Không thể làm mới hồ sơ');
}

const result = refreshProfile();
console.log(result instanceof Promise); // true
~~~

Exception trong async function trở thành rejection của Promise được trả về. Vì vậy, caller cần await trong try/catch hoặc gắn catch vào Promise.

~~~js
try {
  await refreshProfile();
} catch (error) {
  showRefreshError(error);
}
~~~

### 3.4 await làm rejection được ném lại tại vị trí await

~~~js
async function loadProfile() {
  try {
    const response = await fetch('/api/profile');

    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }

    return await response.json();
  } catch (error) {
    console.error('loadProfile thất bại:', error);
    throw error;
  }
}
~~~

await tạm dừng async function cho đến khi Promise settle. Nếu Promise reject, rejection được ném lại như exception tại biểu thức await. try/catch bao quanh await có thể bắt lỗi đó.

Nếu catch ghi log rồi không throw lại, caller sẽ nhận kết quả fulfilled với giá trị trả về của catch, thường là undefined. Chỉ làm vậy khi fallback đó là hành vi có chủ đích.

### 3.5 async event listener có thể tạo unhandled rejection

DOM EventTarget không chờ Promise mà callback async trả về. Ví dụ:

~~~js
button.addEventListener('click', async () => {
  await saveSettings();
});
~~~

Nếu saveSettings() reject, Promise do callback trả về bị EventTarget bỏ qua. Rejection có thể trở thành unhandledrejection.

Cách xử lý:

~~~js
button.addEventListener('click', async () => {
  try {
    await saveSettings();
    showSaved();
  } catch (error) {
    showSaveFailure();
    reportLocalFailure(error);
  }
});
~~~

Hoặc dùng callback đồng bộ và xử lý Promise tường minh:

~~~js
button.addEventListener('click', () => {
  void saveSettings().catch(error => {
    showSaveFailure();
    reportLocalFailure(error);
  });
});
~~~

void không xử lý rejection. Nó chỉ bỏ qua giá trị trả về ở cấp cú pháp; catch mới là phần xử lý lỗi.

### 3.6 catch cũng có thể tạo rejection mới

~~~js
const next = loadData().catch(error => {
  throw new Error('Không thể khôi phục dữ liệu', { cause: error });
});
~~~

catch trả về Promise mới. Nếu callback catch throw hoặc trả về Promise reject, Promise mới cũng reject. Nếu không tiếp tục xử lý next, bạn có thể tạo một unhandled rejection mới dù Promise ban đầu đã có catch.

Khi chuyển lỗi sang tầng khác, giữ nguyên cause nếu hữu ích và bảo đảm Promise mới có caller xử lý.

### 3.7 Promise.all và Promise.allSettled

Promise.all reject khi một input reject. Các Promise khác vẫn tiếp tục thực thi; Promise.all không tự hủy chúng.

~~~js
try {
  const [profile, settings] = await Promise.all([
    loadProfile(),
    loadSettings()
  ]);
} catch (error) {
  showPageLoadFailure();
}
~~~

Dùng Promise.all khi toàn bộ kết quả đều cần thiết. Dùng Promise.allSettled khi muốn thu thập trạng thái từng tác vụ độc lập:

~~~js
const results = await Promise.allSettled([
  loadProfile(),
  loadRecommendations(),
  loadNotifications()
]);

for (const result of results) {
  if (result.status === 'rejected') {
    reportLocalFailure(result.reason);
  }
}
~~~

allSettled không tự báo cáo lỗi. Ứng dụng phải xem từng rejected result và quyết định cách xử lý.

## 4. finally và việc giữ nguyên lỗi gốc

### 4.1 Dùng finally cho cleanup

finally chạy sau try/catch dù thao tác thành công hay thất bại:

~~~js
setLoading(true);

try {
  await saveDocument();
} catch (error) {
  showSaveFailure();
  throw error;
} finally {
  setLoading(false);
}
~~~

Đây là nơi phù hợp để giải phóng lock, đóng spinner, dọn listener tạm hoặc trả tài nguyên.

### 4.2 Không return trong finally khi cần giữ kết quả

~~~js
function riskyOperation() {
  try {
    throw new Error('Lỗi gốc');
  } finally {
    return 'success';
  }
}
~~~

return trong finally có thể ghi đè exception hoặc return trước đó. Tương tự, throw mới trong finally có thể che lỗi ban đầu. Thông thường, finally chỉ nên thực hiện cleanup và không return hoặc throw trừ khi đó là hành vi được thiết kế rõ ràng.

### 4.3 Bọc lỗi nhưng giữ cause

~~~js
async function loadInvoice(id) {
  try {
    return await fetchInvoice(id);
  } catch (cause) {
    throw new Error('Không thể tải hóa đơn', { cause });
  }
}
~~~

cause giúp giữ quan hệ giữa lỗi nghiệp vụ và lỗi thấp hơn. Không đưa toàn bộ cause chain vào telemetry nếu nó có thể chứa URL, dữ liệu request hoặc thông tin nhạy cảm. Chuẩn hóa và lọc trước khi gửi.

## 5. Global error event trên Window

### 5.1 Bắt exception không được xử lý

Window phát error event khi có một số lỗi trong script execution context không được xử lý. Có thể lắng nghe bằng addEventListener:

~~~js
window.addEventListener('error', event => {
  console.error('Uncaught exception', {
    message: event.message,
    filename: event.filename,
    line: event.lineno,
    column: event.colno,
    error: event.error
  });
});
~~~

Với ErrorEvent, các trường hữu ích gồm:

| Trường | Ý nghĩa |
|---|---|
| message | Thông điệp lỗi nếu browser có thể cung cấp |
| filename | URL nguồn script |
| lineno | Dòng nguồn |
| colno | Cột nguồn |
| error | Giá trị Error hoặc đối tượng lỗi nếu được expose |

Các trường có thể rỗng hoặc thiếu thông tin, đặc biệt với lỗi cross-origin. Stack và Error object cũng phụ thuộc browser.

### 5.2 window.onerror là API cũ

Có thể dùng thuộc tính:

~~~js
window.onerror = function (message, source, line, column, error) {
  console.error('Uncaught:', message, source, line, column, error);
};
~~~

window.onerror có chữ ký đặc biệt và hành vi return value khác với event listener thông thường. Trả true có thể ngăn browser ghi thông báo mặc định ra Console. Điều đó không sửa lỗi hoặc phục hồi ứng dụng.

Ưu tiên addEventListener('error', ...) vì API rõ ràng và có thể đăng ký nhiều listener. Không đồng thời cài hai cơ chế nếu không có kế hoạch chống gửi báo cáo trùng.

### 5.3 ErrorEvent khác lỗi tải tài nguyên

Một script hoặc image không tải được cũng phát event tên error, nhưng event đó thường là Event trên element chứ không phải ErrorEvent chứa message/stack.

Các event lỗi tài nguyên không bubble như event thông thường. Muốn quan sát tập trung, dùng capture phase:

~~~js
window.addEventListener('error', event => {
  if (event instanceof ErrorEvent) {
    console.error('Script exception:', event.message);
    return;
  }

  const target = event.target;

  if (target && target !== window) {
    console.warn('Resource load failed:', {
      tag: target.tagName,
      url: target.currentSrc || target.src || target.href
    });
  }
}, true);
~~~

Capture listener có thể nhìn thấy lỗi của resource element khi event đi qua capture path. Hãy phân loại theo event và target; không đọc event.message cho một lỗi tải ảnh rồi mong nhận được nguyên nhân DNS hoặc HTTP chi tiết.

### 5.4 Lỗi resource không cung cấp toàn bộ nguyên nhân

Một img error event chỉ cho biết resource không tải hoặc không giải mã được theo cách browser mong đợi. Nó không nhất thiết cung cấp status HTTP, response body hay nguyên nhân mạng. Dùng Network panel và server logs để điều tra chi tiết.

Nếu script load thất bại, kiểm tra URL, MIME, CSP, CORS, integrity và response status. Không tự động retry vô hạn vì có thể tạo tải lặp hoặc che lỗi cấu hình.

## 6. Promise rejection events

### 6.1 unhandledrejection

Window phát unhandledrejection khi Promise bị reject mà không có rejection handler tại thời điểm browser kiểm tra trạng thái đó:

~~~js
window.addEventListener('unhandledrejection', event => {
  console.error('Unhandled Promise rejection:', event.reason);
});
~~~

event là PromiseRejectionEvent và có hai thuộc tính quan trọng:

- event.promise: Promise bị reject.
- event.reason: giá trị được truyền vào reject() hoặc được throw trong Promise chain.

reason không bắt buộc là Error. Nó có thể là string, number, object, null hoặc bất kỳ JavaScript value nào.

### 6.2 Browser kiểm tra unhandled theo thời điểm của event loop

Promise rejection có thể được xử lý trong cùng lượt microtask trước khi browser phát sự kiện unhandledrejection. Vì vậy, không dựa vào một thời gian cố định như một số mili giây để xác định Promise nào được coi là unhandled.

Điều quan trọng là gắn handler trực tiếp vào Promise chain hoặc await trong try/catch, thay vì trông chờ global event.

### 6.3 rejectionhandled

Một rejection ban đầu chưa có handler có thể được xử lý sau đó. Khi browser đã phát unhandledrejection rồi mới có handler, có thể phát rejectionhandled:

~~~js
window.addEventListener('rejectionhandled', event => {
  console.info('Promise đã được xử lý muộn:', event.promise);
});
~~~

Ví dụ:

~~~js
const pendingFailure = Promise.reject(new Error('Demo late handler'));

setTimeout(() => {
  pendingFailure.catch(() => {
    console.info('Đã gắn handler muộn');
  });
}, 100);
~~~

Browser có thể phát unhandledrejection trước, rồi rejectionhandled sau. Đây là thông tin hữu ích cho telemetry: có thể đánh dấu lỗi ban đầu là late-handled thay vì coi nó như lỗi vẫn chưa được xử lý.

Không tạo Promise rejection có chủ đích trong production chỉ để kiểm tra telemetry. Dùng lab hoặc test riêng.

### 6.4 preventDefault không phải xử lý rejection

unhandledrejection event có thể bị hủy. Gọi event.preventDefault() có thể ngăn hành vi mặc định của browser như ghi cảnh báo vào Console:

~~~js
window.addEventListener('unhandledrejection', event => {
  event.preventDefault();
});
~~~

Không nên làm vậy chỉ để Console sạch hơn. preventDefault không biến Promise thành fulfilled, không phục hồi ứng dụng và không thay thế catch. Chỉ hủy event nếu hệ thống báo cáo có chủ đích và bạn vẫn bảo đảm lỗi được lưu ở nơi phù hợp.

### 6.5 Promise từ script cross-origin có giới hạn báo cáo

Browser có thể không phát unhandledrejection cho rejection bắt nguồn từ script cross-origin vì sự kiện có thể làm lộ dữ liệu giữa các origin. Không giả định global handler quan sát được mọi Promise rejection của mọi script.

Với script bên thứ ba, cấu hình CORS phù hợp nếu cần stack/error details, dùng crossorigin attribute khi phù hợp và phối hợp với nhà cung cấp. Không hạ ranh giới bảo mật chỉ để lấy thêm thông tin lỗi.

## 7. Lỗi từ script cross-origin

### 7.1 Vì sao chỉ thấy "Script error."

Khi classic script được tải từ origin khác mà không bật CORS, browser có thể che chi tiết lỗi để tránh rò rỉ dữ liệu từ script cross-origin. Global error event có thể chỉ cung cấp thông báo chung như Script error. và thiếu filename, dòng, cột hoặc Error object.

### 7.2 Bật CORS cho script khi cần stack

Trang:

~~~html
<script
  src="https://cdn.example.net/app.js"
  crossorigin="anonymous"></script>
~~~

Server của CDN cần trả CORS header cho origin ứng dụng, ví dụ:

~~~http
Access-Control-Allow-Origin: https://app.example.com
~~~

Với tài nguyên công khai có thể dùng wildcard theo chính sách phù hợp. Nếu script cần credentials, phải dùng chế độ credentialed tương ứng và cấu hình origin cụ thể; không dùng wildcard với credentialed CORS.

Module scripts luôn dùng CORS khi tải module graph. Các script module cross-origin cần server cho phép CORS để tải được.

### 7.3 Không mở CORS rộng chỉ để cải thiện log

CORS là quyền đọc response của origin khác. Chỉ cấp cho origin đáng tin và resource cần thiết. Việc mở Access-Control-Allow-Origin cho mọi origin để có stack trace có thể mở rộng quyền truy cập dữ liệu không cần thiết.

### 7.4 Source map và stack trace production

Code bundle/minify có thể làm stack trace khó đọc. Source map giúp ánh xạ vị trí trong bundle về source gốc. Khi phát hành:

- Giữ source map riêng trong hệ thống error monitoring nếu không muốn public.
- Bảo vệ quyền truy cập source map và build artifacts.
- Không nhúng secret, token hoặc dữ liệu môi trường vào source map.
- Lưu release/build identifier để ánh xạ đúng phiên bản.
- Không giả định stack line/column luôn giống nhau giữa browser.

## 8. Lỗi trong Web Worker

### 8.1 Worker có global scope riêng

Dedicated Worker không chạy trong window. Code trong worker không thể dùng window hoặc document. Lỗi phát sinh trong worker cần được quan sát từ Worker object ở phía trang:

~~~js
const worker = new Worker('/worker.js');

worker.addEventListener('error', event => {
  console.error('Worker error:', {
    message: event.message,
    filename: event.filename,
    line: event.lineno,
    column: event.colno
  });
});

worker.addEventListener('messageerror', event => {
  console.error('Không deserialize được message từ worker:', event);
});
~~~

error phản ánh lỗi thực thi trong worker. messageerror phản ánh lỗi deserialize message. Hai loại này có nguyên nhân và cách xử lý khác nhau.

### 8.2 Promise rejection trong worker

Worker có global event context riêng. Nếu cần quan sát unhandled rejection bên trong worker, đăng ký listener trong worker rồi chuyển một báo cáo đã chuẩn hóa về trang bằng postMessage:

~~~js
self.addEventListener('unhandledrejection', event => {
  self.postMessage({
    type: 'worker-unhandled-rejection',
    reason: event.reason instanceof Error
      ? {
          name: event.reason.name,
          message: event.reason.message
        }
      : {
          kind: typeof event.reason
        }
  });
});
~~~

Phía trang phải kiểm tra schema và nguồn message trước khi dùng dữ liệu:

~~~js
worker.addEventListener('message', event => {
  const data = event.data;

  if (
    data === null ||
    typeof data !== 'object' ||
    data.type !== 'worker-unhandled-rejection'
  ) {
    return;
  }

  reportWorkerFailure(data);
});
~~~

Không gửi toàn bộ object lỗi hoặc dữ liệu tùy ý từ worker sang UI. Chỉ chuyển trường được allowlist và có giới hạn kích thước.

### 8.3 Service Worker có công cụ và vòng đời riêng

Service Worker có global scope và lifecycle riêng. Log của nó có thể nằm trong DevTools Application/Service Workers hoặc công cụ tương đương. Worker có thể bị browser dừng khi rảnh; không dựa vào biến global để giữ hàng đợi báo cáo lâu dài.

Nếu cần gửi telemetry từ Service Worker, dùng cơ chế lưu tạm bền vững phù hợp và retry có giới hạn. Đừng coi một fetch report đang chờ là chắc chắn hoàn tất sau khi worker bị terminate.

## 9. Phân biệt lỗi JavaScript với các loại report khác

### 9.1 CSP violation không phải unhandled exception

Content Security Policy có thể phát securitypolicyviolation event khi browser chặn một hành động vi phạm policy:

~~~js
document.addEventListener('securitypolicyviolation', event => {
  console.warn('CSP violation:', {
    directive: event.violatedDirective,
    blockedURI: event.blockedURI,
    sourceFile: event.sourceFile,
    lineNumber: event.lineNumber
  });
});
~~~

Đây là sự kiện bảo mật riêng, không phải JavaScript exception. Có thể có CSP violation mà ứng dụng không ném lỗi JavaScript. Ngược lại, một exception không nhất thiết liên quan CSP.

CSP có thể gửi report qua Reporting API hoặc report-uri theo cơ chế tương ứng. Hãy phân loại telemetry riêng để không trộn lỗi runtime với policy violation.

### 9.2 Network error, HTTP error và resource error

- fetch reject: có thể do network, CORS, abort hoặc lỗi request.
- HTTP 404/500: fetch thường resolve Response; code cần kiểm tra status.
- img error: báo tải/giải mã tài nguyên thất bại, không tự cung cấp đầy đủ HTTP detail.
- script error: có thể do lỗi tải, MIME, CSP, integrity hoặc lỗi thực thi; kiểm tra event và Network.
- unhandledrejection: Promise bị reject mà không có handler đúng thời điểm.
- error event: exception đồng bộ không được xử lý hoặc resource load failure tùy target.

### 9.3 Lỗi nghiệp vụ không phải lúc nào cũng là exception

Một API có thể trả 200 với payload báo validation failure. Một thao tác có thể bị người dùng hủy. Những trường hợp này nên được biểu diễn bằng kết quả nghiệp vụ có kiểu rõ ràng, không nhất thiết ném exception.

Dùng exception cho tình huống thực sự bất thường hoặc không thể tiếp tục luồng hiện tại. Không dùng global error reporting làm hệ thống theo dõi mọi trạng thái nghiệp vụ.

## 10. Thiết kế pipeline báo cáo lỗi an toàn

### 10.1 Xử lý gần nơi lỗi phát sinh trước

Thứ tự ưu tiên:

1. Catch ở nơi có thể khôi phục trạng thái và hiển thị UX phù hợp.
2. Bổ sung ngữ cảnh an toàn như feature, operation và release ID.
3. Gửi báo cáo đã chuẩn hóa nếu lỗi cần điều tra.
4. Dùng global handler làm lớp quan sát cuối cùng cho lỗi bị bỏ sót.

Global handler không biết thao tác nào cần retry, có nên hoàn tác dữ liệu hay người dùng đang ở bước nào. Chỉ component nghiệp vụ mới có đủ thông tin đó.

### 10.2 Chuẩn hóa Error và rejection reason

Không giả định event.reason luôn là Error. Cũng không dùng JSON.stringify(error) để serialize Error vì các thuộc tính quan trọng như message và stack thường không enumerable.

Một normalizer tối thiểu:

~~~js
function safeText(value, maxLength = 300) {
  if (typeof value === 'string') {
    return value.slice(0, maxLength);
  }

  if (
    typeof value === 'number' ||
    typeof value === 'boolean' ||
    typeof value === 'bigint'
  ) {
    return String(value).slice(0, maxLength);
  }

  if (value === null) return 'null';
  if (value === undefined) return 'undefined';

  return '[non-primitive value]';
}

function normalizeReason(reason) {
  try {
    if (reason instanceof Error) {
      return {
        name: safeText(reason.name, 80),
        message: safeText(reason.message, 500),
        stack: typeof reason.stack === 'string'
          ? reason.stack.split('\n').slice(0, 8).join('\n').slice(0, 2000)
          : null
      };
    }
  } catch {
    // Object có thể có getter hoặc proxy gây lỗi khi đọc thuộc tính.
  }

  return {
    name: typeof reason,
    message: safeText(reason, 300),
    stack: null
  };
}
~~~

Normalizer không nên duyệt đệ quy object tùy ý. Proxy, getter, circular reference và object host có thể làm quá trình serialize thất bại hoặc kích hoạt side effect.

### 10.3 Lọc dữ liệu nhạy cảm trước khi gửi

Không gửi mặc định:

- Cookie, Authorization header, access token hoặc refresh token.
- Password, OTP, recovery code hoặc nội dung biểu mẫu.
- Request/response body đầy đủ.
- Query string có thể chứa token hoặc email.
- Toàn bộ localStorage, sessionStorage hoặc IndexedDB.
- Nội dung HTML người dùng hoặc dữ liệu cá nhân không cần cho chẩn đoán.

URL có thể chứa email, mã đơn hàng, token hoặc identifier. Hãy bỏ query/hash và cân nhắc loại bỏ cả path segment nhạy cảm. Message và stack cũng có thể chứa dữ liệu do ứng dụng gắn vào Error; không có một regex tổng quát nào bảo đảm redaction hoàn hảo.

### 10.4 Giới hạn kích thước và tần suất

Một lỗi lặp lại trong vòng lặp hoặc một event bị đăng ký nhiều lần có thể tạo hàng nghìn report. Pipeline nên:

- Giới hạn số report mỗi session và mỗi loại lỗi.
- Gộp lỗi giống nhau theo release, message và vị trí.
- Cắt ngắn message/stack và số field.
- Rate limit ở server theo IP/session và endpoint.
- Giới hạn request body.
- Có sampling cho lỗi phổ biến.
- Không retry vô hạn khi endpoint báo cáo thất bại.

Telemetry không được làm ứng dụng phát sinh thêm lỗi hoặc tạo tải lớn hơn lỗi ban đầu.

### 10.5 Gửi report với fetch keepalive

~~~js
function sendErrorReport(record) {
  const body = JSON.stringify(record);

  if (new TextEncoder().encode(body).byteLength > 12000) {
    return Promise.resolve(false);
  }

  return fetch('/report', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    credentials: 'omit',
    keepalive: true,
    body
  }).then(() => true).catch(() => false);
}
~~~

keepalive cho phép request tiếp tục trong một số tình huống page lifecycle kết thúc, nhưng không bảo đảm server luôn nhận được report. Có giới hạn dữ liệu đang chờ và chính sách browser. Hãy dùng nó như best-effort transport, không coi là hàng đợi bền vững.

navigator.sendBeacon() cũng phù hợp với telemetry nhỏ khi trang sắp rời đi. Beacon không cung cấp response để ứng dụng xác nhận server đã lưu. Endpoint cần chấp nhận kiểu body mà client gửi và validate nội dung như mọi input không tin cậy khác.

### 10.6 Endpoint report cũng là input không tin cậy

Server nhận report phải:

- Chỉ nhận method và content type đã định nghĩa.
- Giới hạn kích thước body trước khi parse.
- Validate schema và độ dài từng field.
- Không render message/stack bằng HTML trong dashboard.
- Rate limit và chống spam.
- Không ghi cookie hoặc header xác thực vào log.
- Xử lý origin/CSRF theo kiến trúc endpoint.
- Có retention và access control phù hợp.
- Không dùng dữ liệu report làm lệnh, SQL hoặc đường dẫn file.

Một client có thể tự tạo report giả. Không dùng telemetry phía browser làm bằng chứng duy nhất cho sự kiện bảo mật hoặc quyết định quyền truy cập.

## 11. Thực hành: bắt lỗi và gửi report bằng Node.js

Lab chạy một trang tại localhost:3000. Browser tạo các lỗi có chủ đích, global handler phân loại chúng rồi gửi JSON nhỏ tới endpoint /report. Server giới hạn body, rate và field được lưu trong terminal.

Lab có các trường hợp:

- Exception đồng bộ trong event handler.
- Exception trong timer callback.
- Promise rejection không có handler.
- Rejection từ async event listener.
- Promise được xử lý ngay.
- Promise được xử lý muộn.
- Lỗi tải image.
- Lỗi trong Dedicated Worker.
- Unhandled rejection được chuyển từ Worker về trang.

Lab chỉ dùng thông điệp demo. Không gửi cookie, token hoặc dữ liệu người dùng.

### 11.1 Cấu trúc thư mục

~~~text
unhandled-exception-lab/
  server.mjs
  public/
    index.html
    app.js
    worker.js
~~~

### 11.2 Tạo server.mjs

~~~js
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const appOrigin = 'http://localhost:3000';
const publicRoot = new URL('./public/', import.meta.url);
const maxBodyBytes = 16 * 1024;
const rateBuckets = new Map();

const files = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/app.js', ['app.js', 'text/javascript; charset=utf-8']],
  ['/worker.js', ['worker.js', 'text/javascript; charset=utf-8']]
]);

function isRateLimited(ip) {
  const now = Date.now();
  const current = rateBuckets.get(ip);

  if (!current || now - current.startedAt > 60000) {
    rateBuckets.set(ip, { startedAt: now, count: 1 });
    return false;
  }

  current.count += 1;
  return current.count > 30;
}

function sendJson(res, status, data) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff'
  });
  res.end(JSON.stringify(data));
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url || '/', appOrigin);

  if (url.pathname === '/report') {
    if (req.method !== 'POST') {
      res.writeHead(405, { 'Allow': 'POST' });
      return res.end();
    }

    if (req.headers.origin && req.headers.origin !== appOrigin) {
      return sendJson(res, 403, { error: 'Origin not allowed' });
    }

    if (!String(req.headers['content-type'] || '')
      .toLowerCase()
      .startsWith('application/json')) {
      return sendJson(res, 415, { error: 'JSON required' });
    }

    const ip = req.socket.remoteAddress || 'unknown';

    if (isRateLimited(ip)) {
      return sendJson(res, 429, { error: 'Rate limited' });
    }

    const chunks = [];
    let size = 0;
    let tooLarge = false;

    req.on('data', chunk => {
      size += chunk.length;

      if (size > maxBodyBytes) {
        tooLarge = true;
        return;
      }

      if (!tooLarge) chunks.push(chunk);
    });

    req.on('end', () => {
      if (tooLarge) {
        return sendJson(res, 413, { error: 'Report too large' });
      }

      let parsed;

      try {
        parsed = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      } catch {
        return sendJson(res, 400, { error: 'Invalid JSON' });
      }

      if (
        parsed === null ||
        typeof parsed !== 'object' ||
        Array.isArray(parsed)
      ) {
        return sendJson(res, 400, { error: 'Invalid report shape' });
      }

      const allowedKinds = new Set([
        'uncaught-exception',
        'unhandled-rejection',
        'rejection-handled-late',
        'resource-load-error',
        'worker-error',
        'worker-unhandled-rejection'
      ]);

      if (
        typeof parsed.kind !== 'string' ||
        !allowedKinds.has(parsed.kind)
      ) {
        return sendJson(res, 400, { error: 'Invalid report kind' });
      }

      const safeRecord = {
        kind: parsed.kind,
        at: typeof parsed.at === 'string'
          ? parsed.at.slice(0, 40)
          : null,
        message: typeof parsed.message === 'string'
          ? parsed.message.slice(0, 500)
          : null,
        name: typeof parsed.name === 'string'
          ? parsed.name.slice(0, 80)
          : null,
        source: typeof parsed.source === 'string'
          ? parsed.source.slice(0, 300)
          : null,
        line: Number.isInteger(parsed.line)
          ? parsed.line
          : null,
        column: Number.isInteger(parsed.column)
          ? parsed.column
          : null,
        promiseId: typeof parsed.promiseId === 'string'
          ? parsed.promiseId.slice(0, 40)
          : null
      };

      console.log('[error-report]', JSON.stringify(safeRecord));
      return sendJson(res, 202, { accepted: true });
    });

    return;
  }

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { 'Allow': 'GET, HEAD' });
    return res.end();
  }

  if (url.pathname === '/missing-image.png') {
    res.writeHead(404, {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff'
    });
    return res.end('Image not found');
  }

  const entry = files.get(url.pathname);

  if (!entry) {
    return sendJson(res, 404, { error: 'Not found' });
  }

  try {
    const body = await readFile(new URL(entry[0], publicRoot));

    res.writeHead(200, {
      'Content-Type': entry[1],
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy':
        "default-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    });

    if (req.method === 'HEAD') return res.end();
    return res.end(body);
  } catch {
    return sendJson(res, 500, { error: 'Cannot read lab file' });
  }
});

server.listen(3000, 'localhost', () => {
  console.log('Unhandled exception lab: http://localhost:3000');
});
~~~

### 11.3 Tạo public/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Unhandled exception lab</title>
  <script src="/app.js" defer></script>
</head>
<body>
  <main>
    <h1>Unhandled exception lab</h1>
    <p id="status" role="status">Đang khởi tạo...</p>

    <section>
      <h2>Exception đồng bộ và callback</h2>
      <button id="sync-error" type="button">Throw trong click handler</button>
      <button id="timer-error" type="button">Throw trong setTimeout</button>
      <button id="resource-error" type="button">Tải image không tồn tại</button>
    </section>

    <section>
      <h2>Promise rejection</h2>
      <button id="unhandled" type="button">Promise reject không catch</button>
      <button id="async-handler" type="button">Async event handler reject</button>
      <button id="handled" type="button">Promise reject có catch</button>
      <button id="late-handler" type="button">Gắn catch muộn</button>
    </section>

    <section>
      <h2>Dedicated Worker</h2>
      <button id="worker-error" type="button">Throw trong Worker</button>
      <button id="worker-rejection" type="button">Unhandled rejection trong Worker</button>
    </section>

    <section>
      <h2>Report gần đây</h2>
      <pre id="reports">Chưa có report.</pre>
    </section>
  </main>
</body>
</html>
~~~

### 11.4 Tạo public/app.js

~~~js
const statusElement = document.querySelector('#status');
const reportsElement = document.querySelector('#reports');
const recentReports = [];
const promiseIds = new WeakMap();
let nextPromiseId = 1;

function safeText(value, maxLength = 300) {
  if (typeof value === 'string') {
    return value.slice(0, maxLength);
  }

  if (
    typeof value === 'number' ||
    typeof value === 'boolean' ||
    typeof value === 'bigint'
  ) {
    return String(value).slice(0, maxLength);
  }

  if (value === null) return 'null';
  if (value === undefined) return 'undefined';

  return '[non-primitive value]';
}

function safeUrl(raw) {
  if (typeof raw !== 'string' || raw.length === 0) return null;

  try {
    const url = new URL(raw, location.href);
    return url.origin + url.pathname;
  } catch {
    return null;
  }
}

function normalizeReason(reason) {
  try {
    if (reason instanceof Error) {
      return {
        name: safeText(reason.name, 80),
        message: safeText(reason.message, 500),
        stack: typeof reason.stack === 'string'
          ? reason.stack.split('\n').slice(0, 6).join('\n').slice(0, 1200)
          : null
      };
    }
  } catch {
    // Bỏ qua Error object có getter hoặc proxy bất thường.
  }

  return {
    name: typeof reason,
    message: safeText(reason, 300),
    stack: null
  };
}

function getPromiseId(promise) {
  let id = promiseIds.get(promise);

  if (!id) {
    id = 'p' + nextPromiseId++;
    promiseIds.set(promise, id);
  }

  return id;
}

function showReport(record) {
  recentReports.unshift(record);

  if (recentReports.length > 12) {
    recentReports.length = 12;
  }

  reportsElement.textContent = JSON.stringify(recentReports, null, 2);
}

function sendReport(input) {
  const record = {
    at: new Date().toISOString(),
    ...input
  };

  showReport(record);

  const body = JSON.stringify(record);

  if (body.length > 6000) return;

  void fetch('/report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'omit',
    keepalive: true,
    body
  }).then(response => {
    if (!response.ok) {
      console.warn('Report endpoint rejected:', response.status);
    }
  }).catch(() => {
    console.warn('Không gửi được error report.');
  });
}

window.addEventListener('error', event => {
  if (event instanceof ErrorEvent) {
    const normalized = normalizeReason(event.error);

    sendReport({
      kind: 'uncaught-exception',
      name: normalized.name,
      message: safeText(event.message || normalized.message, 500),
      source: safeUrl(event.filename),
      line: Number.isInteger(event.lineno) ? event.lineno : null,
      column: Number.isInteger(event.colno) ? event.colno : null
    });

    return;
  }

  const target = event.target;

  if (target && target !== window) {
    sendReport({
      kind: 'resource-load-error',
      name: safeText(target.tagName, 40),
      message: 'Resource failed to load',
      source: safeUrl(
        target.currentSrc || target.src || target.href || ''
      )
    });
  }
}, true);

window.addEventListener('unhandledrejection', event => {
  const normalized = normalizeReason(event.reason);

  sendReport({
    kind: 'unhandled-rejection',
    promiseId: getPromiseId(event.promise),
    name: normalized.name,
    message: normalized.message
  });
});

window.addEventListener('rejectionhandled', event => {
  const normalized = normalizeReason(event.reason);

  sendReport({
    kind: 'rejection-handled-late',
    promiseId: getPromiseId(event.promise),
    name: normalized.name,
    message: normalized.message
  });
});

document.querySelector('#sync-error').addEventListener('click', () => {
  throw new Error('Demo: synchronous click handler failed');
});

document.querySelector('#timer-error').addEventListener('click', () => {
  setTimeout(() => {
    throw new Error('Demo: timer callback failed');
  }, 0);
});

document.querySelector('#resource-error').addEventListener('click', () => {
  const image = document.createElement('img');
  image.alt = 'Missing image demo';
  image.src = '/missing-image.png';
  document.body.append(image);
});

document.querySelector('#unhandled').addEventListener('click', () => {
  Promise.reject(new Error('Demo: unhandled Promise rejection'));
});

document.querySelector('#async-handler').addEventListener('click', async () => {
  await Promise.reject(new Error('Demo: async event listener rejection'));
});

document.querySelector('#handled').addEventListener('click', () => {
  Promise.reject(new Error('Demo: handled rejection')).catch(error => {
    statusElement.textContent =
      'Đã xử lý cục bộ: ' + safeText(error.message, 200);
  });
});

document.querySelector('#late-handler').addEventListener('click', () => {
  const failure = Promise.reject(new Error('Demo: late handler'));

  setTimeout(() => {
    failure.catch(() => {
      statusElement.textContent = 'Đã gắn catch sau khi rejection xảy ra.';
    });
  }, 150);
});

const worker = new Worker('/worker.js');

worker.addEventListener('error', event => {
  sendReport({
    kind: 'worker-error',
    message: safeText(event.message || 'Worker execution failed', 500),
    source: safeUrl(event.filename),
    line: Number.isInteger(event.lineno) ? event.lineno : null,
    column: Number.isInteger(event.colno) ? event.colno : null
  });
});

worker.addEventListener('messageerror', () => {
  statusElement.textContent = 'Không deserialize được message từ Worker.';
});

worker.addEventListener('message', event => {
  const data = event.data;

  if (
    data === null ||
    typeof data !== 'object' ||
    Array.isArray(data) ||
    data.type !== 'worker-unhandled-rejection'
  ) {
    return;
  }

  sendReport({
    kind: 'worker-unhandled-rejection',
    name: safeText(data.name, 80),
    message: safeText(data.message, 300)
  });
});

document.querySelector('#worker-error').addEventListener('click', () => {
  worker.postMessage({ type: 'throw' });
});

document.querySelector('#worker-rejection').addEventListener('click', () => {
  worker.postMessage({ type: 'reject' });
});

statusElement.textContent = 'Global error listeners đã sẵn sàng.';
~~~

### 11.5 Tạo public/worker.js

~~~js
self.addEventListener('unhandledrejection', event => {
  const reason = event.reason;
  let name = typeof reason;
  let message = '[non-Error rejection]';

  try {
    if (reason instanceof Error) {
      name = reason.name;
      message = reason.message;
    }
  } catch {
    message = '[unreadable rejection reason]';
  }

  self.postMessage({
    type: 'worker-unhandled-rejection',
    name: String(name).slice(0, 80),
    message: String(message).slice(0, 300)
  });
});

self.addEventListener('message', event => {
  const data = event.data;

  if (!data || typeof data !== 'object') return;

  if (data.type === 'throw') {
    setTimeout(() => {
      throw new Error('Demo: uncaught exception in Dedicated Worker');
    }, 0);
  }

  if (data.type === 'reject') {
    Promise.reject(new Error('Demo: unhandled rejection in Dedicated Worker'));
  }
});
~~~

### 11.6 Chạy lab

Từ thư mục unhandled-exception-lab:

~~~bash
node server.mjs
~~~

Mở:

~~~text
http://localhost:3000
~~~

Không cần cài package ngoài. Dùng localhost để có secure context cho các API browser yêu cầu. Mở DevTools → Console và Network để quan sát event cùng POST tới /report.

### 11.7 Thử exception đồng bộ và timer

Bấm “Throw trong click handler”. Browser phát global error event; trang thêm một report có kind là uncaught-exception.

Bấm “Throw trong setTimeout”. try/catch ở nơi đăng ký timer không tồn tại trong lab, vì vậy lỗi phát sinh khi callback chạy và được global handler quan sát.

Mở Console để thấy exception vẫn được browser báo. Global handler không làm cho exception trở thành lỗi đã được xử lý tại nghiệp vụ.

### 11.8 Thử Promise rejection

Bấm “Promise reject không catch”. Browser phát unhandledrejection và report có promiseId.

Bấm “Async event handler reject”. DOM EventTarget không chờ Promise từ callback async, vì vậy rejection có thể trở thành unhandled.

Bấm “Promise reject có catch”. Không có unhandledrejection vì Promise được xử lý trong chain. Trang hiển thị thông báo xử lý cục bộ.

Bấm “Gắn catch muộn”. Browser có thể phát unhandledrejection trước rồi rejectionhandled sau. Đối chiếu hai report dùng cùng promiseId.

### 11.9 Thử lỗi tải tài nguyên

Bấm “Tải image không tồn tại”. Image request trả 404 và tạo resource error event. Handler dùng capture phase để quan sát event từ element.

Mở Network để xem HTTP 404. Đây là ví dụ cho thấy event error trên element không nhất thiết cung cấp status hoặc response body cho handler.

### 11.10 Thử lỗi trong Worker

Bấm “Throw trong Worker”. Trang nhận error event từ Worker object và gửi worker-error report.

Bấm “Unhandled rejection trong Worker”. Worker tự nghe unhandledrejection rồi postMessage dữ liệu đã chuẩn hóa về trang. Trang kiểm tra schema trước khi gửi report.

Worker có global scope riêng; listener trên window không trực tiếp bắt Promise rejection nội bộ của worker.

### 11.11 Kiểm tra report endpoint

Trong terminal chạy Node, quan sát các dòng [error-report]. Server chỉ log các field được allowlist và cắt độ dài.

Thử gửi JSON sai định dạng, method khác POST hoặc body vượt giới hạn bằng công cụ kiểm thử riêng. Endpoint trả 400, 405 hoặc 413 theo trường hợp. Không gửi dữ liệu bí mật vào lab.

### 11.12 Dừng lab

Dừng server bằng Ctrl+C. Reload trang sau khi server dừng sẽ không gửi được report; điều đó không ảnh hưởng tới hành vi bắt lỗi trong tab hiện tại.

## 12. Chẩn đoán lỗi unhandled exception

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| try/catch không bắt lỗi timer | Callback chạy sau khi try kết thúc | Đặt try/catch bên trong callback |
| try/catch không bắt rejection | Promise không được await hoặc không có catch | await trong try/catch hoặc gắn catch |
| async click handler tạo unhandledrejection | EventTarget bỏ qua Promise callback trả về | Catch bên trong handler |
| catch đã có nhưng vẫn unhandled | Promise mới từ catch/then lại reject | Theo dõi toàn bộ chain và xử lý Promise cuối |
| Global error không thấy Promise rejection | Đang nghe sai event | Đăng ký unhandledrejection |
| unhandledrejection không có stack | reason không phải Error hoặc browser che thông tin | Chuẩn hóa theo kiểu, kiểm tra CORS với script ngoài |
| Chỉ thấy Script error. | Classic script cross-origin không có CORS | Dùng crossorigin và CORS header đúng nếu cần |
| Lỗi image không có status | Resource error event không expose HTTP detail | Kiểm tra Network/server logs |
| Worker lỗi nhưng window không thấy | Worker có global scope riêng | Nghe error/messageerror trên Worker và chuyển report có schema |
| Report gửi trùng nhiều lần | Nhiều listener, lỗi lặp hoặc cùng lỗi ở local/global handler | Deduplicate theo release/message/stack và correlation ID |
| Report endpoint không nhận request | CSP connect-src, mạng, unload hoặc endpoint lỗi | Kiểm tra Network, CSP và server |
| Server log quá nhiều report | Không rate limit hoặc lỗi lặp | Sampling, grouping, rate limit và giới hạn payload |
| Report chứa token hoặc email | Message/stack/URL có dữ liệu nhạy cảm | Redact trước gửi, allowlist field và bỏ query |
| Global handler làm Console im lặng | preventDefault hoặc onerror return true | Chỉ hủy hành vi mặc định khi có chủ đích |

## 13. Ma trận kiểm thử

| ID | Tình huống | Kết quả cần xác nhận |
|---|---|---|
| E01 | throw trong function có try/catch | Catch cục bộ nhận Error |
| E02 | throw trong event callback không catch | Global error event |
| E03 | throw trong setTimeout callback | Global error event ở callback task |
| E04 | throw trong Promise.then | Promise kế tiếp reject |
| E05 | Promise reject có catch ngay | Không phát unhandledrejection |
| E06 | Promise reject không catch | Có thể phát unhandledrejection |
| E07 | Gắn catch sau đó | Có thể phát rejectionhandled |
| E08 | async event listener reject | Rejection được xử lý cục bộ hoặc thành unhandled |
| E09 | catch callback tự throw | Promise mới reject |
| E10 | finally return | Xác nhận có thể ghi đè kết quả/lỗi; không dùng trong cleanup thông thường |
| E11 | image 404 | Resource error event ở capture phase |
| E12 | script cross-origin không CORS | Error detail có thể bị che |
| E13 | script cross-origin có crossorigin và ACAO | Có thể nhận thêm chi tiết lỗi |
| E14 | Worker throw | Worker object phát error |
| E15 | Worker Promise reject | Worker listener chuyển report qua postMessage |
| E16 | Worker message không đúng schema | Trang bỏ qua message |
| E17 | fetch trả HTTP 404 | Promise resolve Response; code kiểm tra status |
| E18 | fetch bị CORS/network reject | Promise reject |
| E19 | report body quá lớn | Server trả 413 |
| E20 | report kind ngoài allowlist | Server trả 400 |
| E21 | report gửi quá tần suất | Server trả 429 |
| E22 | URL report có query nhạy cảm | Client bỏ query trước khi gửi |
| E23 | CSP chặn kết nối report | Network/Console cho biết connect-src violation |
| E24 | nhiều report cùng lỗi | Grouping/sampling giảm bản ghi trùng |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Unhandled exception là gì?

**Đáp án:** Là exception không tìm thấy handler phù hợp trong luồng thực thi hiện tại. Browser có thể báo qua global error event, nhưng điều đó không tự phục hồi ứng dụng.

**Câu 2.** Vì sao try/catch bên ngoài setTimeout không bắt được lỗi trong callback?

**Đáp án:** Callback chạy ở task khác sau khi khối try/catch ban đầu đã kết thúc. Đặt catch bên trong callback hoặc xử lý Promise mà callback trả về.

**Câu 3.** async function biểu diễn lỗi như thế nào?

**Đáp án:** async function luôn trả Promise. Exception trong function trở thành rejection của Promise đó; caller cần await trong try/catch hoặc gắn catch.

**Câu 4.** Vì sao async event listener có thể tạo unhandledrejection?

**Đáp án:** DOM EventTarget không chờ Promise mà listener async trả về. Rejection không được xử lý sẽ lọt ra global scope.

**Câu 5.** error và unhandledrejection khác nhau thế nào?

**Đáp án:** error thường quan sát exception không được bắt và một số lỗi tài nguyên; unhandledrejection quan sát Promise rejection chưa có handler đúng thời điểm.

**Câu 6.** rejectionhandled có ý nghĩa gì?

**Đáp án:** Một Promise đã bị báo unhandled sau đó được gắn rejection handler. Sự kiện giúp telemetry nhận diện lỗi được xử lý muộn.

**Câu 7.** Vì sao event.reason không luôn là Error?

**Đáp án:** Promise có thể reject với bất kỳ JavaScript value nào. Normalizer phải xử lý primitive và object không tin cậy.

**Câu 8.** Vì sao global error handler không nên thay catch nghiệp vụ?

**Đáp án:** Global handler không biết cách phục hồi state hoặc UX phù hợp. Nó chỉ là lớp quan sát cuối cùng và không đảo ngược thao tác đã xảy ra.

**Câu 9.** Vì sao script cross-origin có thể chỉ báo Script error.?

**Đáp án:** Browser che thông tin lỗi để ngăn rò rỉ dữ liệu cross-origin khi script không được tải với CORS phù hợp.

**Câu 10.** Vì sao error report phải được giới hạn và lọc?

**Đáp án:** Message, stack và URL có thể chứa bí mật hoặc dữ liệu cá nhân; lỗi lặp có thể tạo lượng request lớn. Cần allowlist, redaction, giới hạn kích thước và rate limit.

## 15. Checklist triển khai

### Xử lý lỗi tại nguồn

- [ ] Dùng Error object thay vì throw string hoặc object tùy ý.
- [ ] Catch exception ở nơi có thể khôi phục state.
- [ ] Await Promise trong try/catch hoặc gắn catch cho Promise cuối.
- [ ] Xử lý rejection trong async event listener.
- [ ] Không dùng catch rỗng để che lỗi.
- [ ] Không return/throw tùy tiện trong finally.
- [ ] Phân biệt lỗi kỹ thuật với kết quả nghiệp vụ.

### Global events và execution context

- [ ] Đăng ký window error bằng addEventListener.
- [ ] Dùng capture phase khi cần quan sát resource load errors.
- [ ] Đăng ký unhandledrejection và rejectionhandled.
- [ ] Không giả định global handler quan sát mọi script cross-origin.
- [ ] Nghe error và messageerror trên Worker.
- [ ] Chuyển worker rejection bằng message có schema rõ ràng.
- [ ] Kiểm tra đúng frame/worker trong DevTools.

### Báo cáo và quyền riêng tư

- [ ] Chuẩn hóa Error và non-Error rejection reason.
- [ ] Không JSON.stringify Error hoặc object tùy ý một cách mù quáng.
- [ ] Bỏ token, cookie, password, OTP và dữ liệu form.
- [ ] Redact query string và identifier nhạy cảm trong URL/stack.
- [ ] Giới hạn message, stack và payload.
- [ ] Deduplicate, sampling và rate limit.
- [ ] Dùng keepalive/sendBeacon như best-effort, không coi là bảo đảm.
- [ ] Validate report ở server và không render bằng HTML.
- [ ] Không dùng browser report làm căn cứ authorization.
- [ ] Phân loại CSP violation, network error và lỗi nghiệp vụ riêng.

### Kiểm thử và vận hành

- [ ] Test sync throw, timer, Promise rejection và async listener.
- [ ] Test late handler và rejectionhandled.
- [ ] Test resource error và cross-origin script.
- [ ] Test Worker error/rejection.
- [ ] Kiểm tra CSP connect-src cho report endpoint.
- [ ] Kiểm tra server body limit và rate limit.
- [ ] Có release ID/source map phù hợp để điều tra production.
- [ ] Theo dõi tỷ lệ lỗi và endpoint health mà không log secret.

**Ghi nhớ:** Global error event và unhandledrejection giúp phát hiện lỗi lọt khỏi xử lý cục bộ. Chúng là cơ chế quan sát, không phải cơ chế phục hồi. Hãy xử lý Promise ở đúng caller, giữ riêng execution context của Worker, phân loại lỗi resource và CSP, rồi gửi telemetry đã chuẩn hóa, lọc dữ liệu và giới hạn tài nguyên.

## Tài liệu tham khảo

- [WHATWG — HTML Standard: Runtime script errors](https://html.spec.whatwg.org/multipage/webappapis.html#runtime-script-errors)
- [WHATWG — HTML Standard: Unhandled promise rejections](https://html.spec.whatwg.org/multipage/webappapis.html#unhandled-promise-rejections)
- [MDN — Window: error event](https://developer.mozilla.org/en-US/docs/Web/API/Window/error_event)
- [MDN — Window: unhandledrejection event](https://developer.mozilla.org/en-US/docs/Web/API/Window/unhandledrejection_event)
- [MDN — Window: rejectionhandled event](https://developer.mozilla.org/en-US/docs/Web/API/Window/rejectionhandled_event)
- [MDN — PromiseRejectionEvent](https://developer.mozilla.org/en-US/docs/Web/API/PromiseRejectionEvent)
- [MDN — Error](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Error)
- [MDN — Promise](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise)
- [MDN — Worker: error event](https://developer.mozilla.org/en-US/docs/Web/API/Worker/error_event)
- [MDN — WorkerGlobalScope: unhandledrejection event](https://developer.mozilla.org/en-US/docs/Web/API/WorkerGlobalScope/unhandledrejection_event)
- [MDN — Window: securitypolicyviolation event](https://developer.mozilla.org/en-US/docs/Web/API/Document/securitypolicyviolation_event)

