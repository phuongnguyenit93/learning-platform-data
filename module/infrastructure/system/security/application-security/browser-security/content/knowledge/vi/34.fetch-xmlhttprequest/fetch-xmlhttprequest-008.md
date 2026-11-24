# Abort request

> **Chương:** Fetch và XMLHttpRequest  
> **Chủ đề:** Abort request  
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao ứng dụng cần hủy request khi người dùng đổi ý, rời màn hình hoặc request vượt thời gian chờ.
2. Dùng AbortController và AbortSignal để hủy một hoặc nhiều request Fetch.
3. Phân biệt hủy request trước khi nhận response với hủy trong lúc đọc response body.
4. Kết hợp hủy thủ công, timeout và nhiều điều kiện hủy bằng AbortSignal.timeout() và AbortSignal.any().
5. Dùng XMLHttpRequest.abort() và tích hợp XHR với AbortSignal.
6. Quản lý race condition, request cũ và cleanup khi component hoặc trang kết thúc.
7. Hiểu giới hạn của client-side cancellation đối với xử lý đang chạy ở server.
8. Kiểm thử abort behavior bằng DevTools và một lab Node.js local.

## 1. Abort request là gì?

Một request bất đồng bộ có thể mất thời gian do mạng chậm, server bận, response lớn hoặc người dùng rời khỏi chức năng đang tải. Nếu kết quả không còn cần thiết, ứng dụng nên dừng việc chờ và xử lý response đó.

Các tình huống thường gặp:

- Người dùng nhập từ khóa mới khi request tìm kiếm trước vẫn đang chạy.
- Người dùng đổi trang hoặc đóng dialog trong khi dữ liệu đang tải.
- Một màn hình có nhiều request con; chỉ cần một thao tác hủy để kết thúc cả nhóm.
- Request vượt quá thời gian chờ mà giao diện chấp nhận.
- Một request cũ trả về sau request mới và có nguy cơ ghi đè dữ liệu mới hơn.
- Ứng dụng đang đọc response body dạng stream nhưng người dùng không cần phần dữ liệu còn lại.

Browser cung cấp AbortController và AbortSignal để truyền tín hiệu hủy tới các API hỗ trợ. fetch() nhận signal trong options. Khi controller abort, Fetch dừng việc chờ response hoặc đọc body và Promise liên quan bị reject.

Hủy request là một phần của quản lý vòng đời tác vụ. Nó giúp giảm công việc không cần thiết ở client, giải phóng tài nguyên và tránh cập nhật giao diện bằng dữ liệu đã lỗi thời.

## 2. AbortController và AbortSignal

AbortController là đối tượng ứng dụng dùng để phát tín hiệu hủy. controller.signal là đối tượng AbortSignal được truyền tới API cần hỗ trợ hủy.

```js
const controller = new AbortController();
const signal = controller.signal;

fetch('/api/products', { signal });

// Khi không còn cần request:
controller.abort();
```

Vai trò của từng đối tượng:

| Thành phần | Vai trò |
|---|---|
| AbortController | Nơi ứng dụng gọi abort() để phát tín hiệu |
| AbortSignal | Tín hiệu chỉ đọc được API nhận; có aborted, reason và sự kiện abort |
| controller.abort() | Đánh dấu signal đã bị abort và thông báo cho các consumer |
| signal.aborted | Cho biết signal đã bị hủy hay chưa |
| signal.reason | Lý do hủy; mặc định thường là DOMException tên AbortError |

### 2.1. Hủy một Fetch cơ bản

```js
const controller = new AbortController();
const cancelButton = document.querySelector('#cancel');
const cancelRequest = () => controller.abort();

cancelButton.addEventListener('click', cancelRequest, { once: true });

try {
  const response = await fetch('/api/report', {
    signal: controller.signal,
  });

  if (!response.ok) {
    throw new Error('HTTP status: ' + response.status);
  }

  const report = await response.json();
  renderReport(report);
} catch (error) {
  if (controller.signal.aborted) {
    console.log('Request đã bị hủy.');
  } else {
    console.error('Không tải được report:', error);
  }
} finally {
  cancelButton.removeEventListener('click', cancelRequest);
}

```

Khi người dùng nhấn nút Cancel, callback gọi abort() và Fetch reject. Có thể gọi cùng hàm cancelRequest từ cleanup khi người dùng đổi route hoặc component bị tháo khỏi giao diện.

### 2.2. Signal chỉ dùng một lần

Một signal đã abort sẽ giữ trạng thái aborted === true. Không thể reset signal để dùng cho request tiếp theo. Khi bắt đầu một tác vụ mới, tạo controller mới:

```js
let activeController = null;

async function loadResults() {
  activeController?.abort();

  const controller = new AbortController();
  activeController = controller;

  try {
    const response = await fetch('/api/search', {
      signal: controller.signal,
    });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return await response.json();
  } finally {
    if (activeController === controller) {
      activeController = null;
    }
  }
}

function cancelResults() {
  activeController?.abort();
}
```

Mẫu này hủy request trước đó khi một lần tải mới bắt đầu. So sánh controller theo identity trong finally để một request cũ không xóa nhầm controller của request mới.

### 2.3. Lý do hủy tùy chỉnh

Có thể truyền reason cho abort():

```js
const controller = new AbortController();

controller.abort(new DOMException(
  'Người dùng rời màn hình',
  'AbortError'
));

console.log(controller.signal.aborted);
console.log(controller.signal.reason);
```

Nếu không truyền reason, browser dùng AbortError mặc định. Nếu truyền một object hoặc Error tùy chỉnh, API nhận signal có thể reject bằng reason đó. Vì vậy, không phải mọi lỗi do abort đều có name === 'AbortError'; hãy kiểm tra signal hoặc reason theo cách phù hợp với ứng dụng.

Có thể kiểm tra trước khi làm thêm việc:

```js
signal.throwIfAborted();
```

throwIfAborted() ném signal.reason nếu signal đã abort. Đây là cách tiện để dừng một chuỗi xử lý bất đồng bộ trước khi thực hiện bước tiếp theo.

## 3. Abort trong các giai đoạn của Fetch

Fetch có nhiều giai đoạn: gửi request, chờ response headers, nhận response và đọc body. Abort có thể xảy ra ở các thời điểm khác nhau.

### 3.1. Abort trước khi response headers tới

Nếu request bị hủy khi browser còn đang chờ server, Promise từ fetch() reject. Không có response để ứng dụng xử lý:

```js
const controller = new AbortController();
const request = fetch('/api/slow', {
  signal: controller.signal,
});

controller.abort();

try {
  await request;
} catch (error) {
  console.log('Fetch rejected:', error.name);
}
```

Trong thực tế, abort() có thể được gọi sau một khoảng thời gian hoặc từ một tương tác khác. Đoạn code trên chỉ minh họa trường hợp hủy ngay.

### 3.2. Abort sau khi nhận headers nhưng đang đọc body

fetch() thường resolve khi response headers đã sẵn sàng, ngay cả khi body còn đang truyền. Nếu signal bị abort sau thời điểm đó, việc đọc body vẫn có thể reject:

```js
const controller = new AbortController();

const response = await fetch('/api/large-export', {
  signal: controller.signal,
});

// Headers đã nhận; body có thể vẫn đang tải.
const bodyPromise = response.text();

controller.abort();

try {
  await bodyPromise;
} catch (error) {
  console.log('Đọc body bị dừng:', error.name);
}
```

Điều này quan trọng với response lớn hoặc streaming. Việc fetch() đã resolve không có nghĩa toàn bộ dữ liệu đã được tải.

### 3.3. Hủy khi đọc ReadableStream

Với response body dạng stream, ứng dụng có thể đọc từng chunk:

```js
const controller = new AbortController();
const response = await fetch('/api/events', {
  signal: controller.signal,
});

const reader = response.body.getReader();

try {
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    processChunk(value);
  }
} catch (error) {
  if (controller.signal.aborted) {
    console.log('Stream bị hủy:', controller.signal.reason);
  } else {
    throw error;
  }
} finally {
  reader.releaseLock();
}
```

Khi signal abort, thao tác đọc body sẽ bị ảnh hưởng. Nếu ứng dụng chủ động dừng reader mà không hủy toàn bộ Fetch, có thể gọi reader.cancel(reason); cần hiểu rõ API và luồng dữ liệu để không giữ lock hoặc tiếp tục xử lý chunk sau khi tác vụ kết thúc.

## 4. Timeout và kết hợp nhiều tín hiệu hủy

Nhiều request cần giới hạn thời gian chờ. Có thể dùng AbortSignal.timeout():

```js
try {
  const response = await fetch('/api/summary', {
    signal: AbortSignal.timeout(5000),
  });

  if (!response.ok) throw new Error('HTTP ' + response.status);
  const summary = await response.json();
  renderSummary(summary);
} catch (error) {
  if (error.name === 'TimeoutError') {
    showMessage('Request vượt quá thời gian chờ.');
  } else if (error.name === 'AbortError') {
    showMessage('Request đã bị hủy.');
  } else {
    showMessage('Không thể tải dữ liệu.');
  }
}
```

AbortSignal.timeout(ms) tạo một signal tự abort sau thời gian được chỉ định. Trên browser hiện đại, reason thường là TimeoutError. Timeout của API này đo active time; nó có thể tạm dừng khi document ở back-forward cache hoặc worker bị suspend, vì vậy không nhất thiết tương đương một deadline theo đồng hồ thực.

### 4.1. Kết hợp người dùng hủy và timeout

Một request có thể bị hủy vì người dùng nhấn Cancel hoặc vì hết thời gian chờ. AbortSignal.any() tạo signal mới abort khi bất kỳ signal đầu vào nào abort:

```js
const userController = new AbortController();
const timeoutSignal = AbortSignal.timeout(8000);

const signal = AbortSignal.any([
  userController.signal,
  timeoutSignal,
]);

try {
  const response = await fetch('/api/report', { signal });
  if (!response.ok) throw new Error('HTTP ' + response.status);
  renderReport(await response.json());
} catch (error) {
  if (signal.aborted && signal.reason?.name === 'TimeoutError') {
    showMessage('Server phản hồi quá chậm.');
  } else if (signal.aborted) {
    showMessage('Bạn đã hủy thao tác.');
  } else {
    showMessage('Có lỗi khi tải báo cáo.');
  }
}

function cancelByUser() {
  userController.abort();
}
```

Reason của signal kết hợp phản ánh lý do từ signal đầu tiên làm nó abort. Kiểm tra signal.aborted cùng signal.reason giúp phân biệt timeout với thao tác hủy chủ động.

AbortSignal.any() và AbortSignal.timeout() có thể không có trên browser cũ. Kiểm tra hỗ trợ trước khi dùng nếu sản phẩm cần hỗ trợ các browser đó:

```js
const supportsTimeout = typeof AbortSignal.timeout === 'function';
const supportsAny = typeof AbortSignal.any === 'function';
```

Nếu cần tương thích rộng, có thể tự tạo controller, dùng setTimeout() để gọi abort() và nối sự kiện abort từ các signal nguồn. Khi request hoàn tất, phải clear timer và gỡ các listener đã đăng ký.

### 4.2. Timeout thủ công

```js
const controller = new AbortController();
const timer = setTimeout(() => {
  controller.abort(new DOMException('Request timeout', 'TimeoutError'));
}, 5000);

try {
  const response = await fetch('/api/summary', {
    signal: controller.signal,
  });
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return await response.json();
} finally {
  clearTimeout(timer);
}
```

Không quên clearTimeout() trong finally; nếu request kết thúc sớm mà timer vẫn tồn tại, callback có thể abort một tác vụ đã hoàn tất hoặc giữ tài nguyên không cần thiết.

## 5. Hủy XMLHttpRequest

XMLHttpRequest có phương thức abort() riêng. Khác với Fetch, XHR không nhận AbortSignal trong open() hoặc send().

Ví dụ:

```js
const xhr = new XMLHttpRequest();
const cancelButton = document.querySelector('#cancel');
const cancelRequest = () => xhr.abort();

xhr.open('GET', '/api/slow');
xhr.onload = () => {
  console.log('HTTP status:', xhr.status);
  console.log('Response:', xhr.responseText);
};
xhr.onerror = () => {
  console.error('Network error');
};
xhr.onabort = () => {
  console.log('XHR request was aborted');
};
xhr.onloadend = () => {
  console.log('XHR finished or aborted');
  cancelButton.removeEventListener('click', cancelRequest);
};

cancelButton.addEventListener('click', cancelRequest, { once: true });
xhr.send();

```

Khi người dùng nhấn nút Cancel, xhr.abort() dừng request và phát sự kiện abort; loadend cũng được phát khi quá trình kết thúc. Handler load không phải nơi xử lý nhánh abort. Kiểm tra status và sự kiện phù hợp để phân biệt hoàn tất, lỗi mạng, timeout và hủy.

### 5.1. Kết nối AbortSignal với XHR

Có thể tạo adapter để code dùng một kiểu hủy chung:

```js
function xhrRequest(url, { signal, timeout = 0 } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let settled = false;

    const cleanup = () => {
      signal?.removeEventListener('abort', abortXhr);
    };

    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      cleanup();
      callback(value);
    };

    const abortXhr = () => xhr.abort();

    if (signal?.aborted) {
      finish(
        reject,
        signal.reason ?? new DOMException('Aborted', 'AbortError')
      );
      return;
    }

    signal?.addEventListener('abort', abortXhr, { once: true });

    xhr.open('GET', url);
    xhr.timeout = timeout;
    xhr.onload = () => finish(resolve, {
      status: xhr.status,
      body: xhr.responseText,
    });
    xhr.onerror = () => finish(reject, new TypeError('Network error'));
    xhr.onabort = () => finish(
      reject,
      signal?.reason ?? new DOMException('Aborted', 'AbortError')
    );
    xhr.ontimeout = () => finish(
      reject,
      new DOMException('XHR timeout', 'TimeoutError')
    );

    xhr.send();
  });
}

const controller = new AbortController();
xhrRequest('/api/slow', {
  signal: controller.signal,
  timeout: 10000,
}).then(renderResult).catch(handleRequestError);

// Khi cần hủy:
controller.abort();
```

Adapter kiểm tra signal.aborted trước khi gửi, lắng nghe sự kiện abort và gỡ listener khi Promise kết thúc. Đây là ví dụ cơ bản; ứng dụng có thể mở rộng method, headers, body, responseType và status handling theo nhu cầu.

xhr.timeout là timeout riêng của XHR. Nếu vừa dùng timeout của XHR vừa dùng signal timeout, cần quy định rõ lớp nào sở hữu thông báo lỗi để tránh xử lý trùng.

## 6. Quản lý vòng đời và cleanup

Controller nên thuộc về đúng tác vụ hoặc nhóm tác vụ. Tránh một controller global dùng cho mọi request của ứng dụng; một thao tác hủy khi đó có thể dừng cả request không liên quan.

### 6.1. Hủy khi component rời màn hình

Trong framework UI, tạo controller khi bắt đầu effect/tác vụ và abort trong cleanup:

```js
useEffect(() => {
  const controller = new AbortController();

  fetch('/api/profile', { signal: controller.signal })
    .then((response) => {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    })
    .then(setProfile)
    .catch((error) => {
      if (!controller.signal.aborted) {
        setError(error);
      }
    });

  return () => controller.abort();
}, []);
```

Đây là ví dụ theo phong cách React. Với framework khác, dùng lifecycle cleanup tương ứng. Nếu signal có thể abort bằng custom reason, đừng chỉ kiểm tra error.name; kiểm tra controller.signal.aborted để bỏ qua lỗi do hủy.

### 6.2. Hủy listener DOM bằng signal

AbortSignal còn có thể quản lý listener:

```js
const controller = new AbortController();

window.addEventListener('resize', handleResize, {
  signal: controller.signal,
});

document.addEventListener('visibilitychange', handleVisibility, {
  signal: controller.signal,
});

// Gỡ cả hai listener cùng lúc:
controller.abort();
```

Khi signal abort, browser tự gỡ listener được đăng ký với signal đó. Cách này hữu ích cho listener gắn với một màn hình hoặc một tác vụ có vòng đời rõ ràng.

### 6.3. Một controller cho nhiều request liên quan

Một signal có thể được truyền cho nhiều Fetch. Khi controller abort, tất cả operation hỗ trợ signal đó đều nhận tín hiệu hủy:

```js
const controller = new AbortController();

const requests = [
  fetch('/api/profile', { signal: controller.signal }),
  fetch('/api/notifications', { signal: controller.signal }),
  fetch('/api/preferences', { signal: controller.signal }),
];

const resultsPromise = Promise.all(requests);

// Gắn hàm này vào nút Cancel hoặc cleanup của màn hình.
function cancelScreenRequests() {
  controller.abort();
}

try {
  const results = await resultsPromise;
  renderDashboard(results);
} catch (error) {
  if (!controller.signal.aborted) throw error;
}
```

Trong ứng dụng thực tế, cần bắt lỗi Promise và gọi abort từ callback phù hợp. Nếu dùng Promise.all(), một request reject sẽ làm Promise.all reject, nhưng các request còn lại không tự động bị hủy; controller chung giúp hủy chúng khi nhóm không còn cần.

## 7. Abort không giải quyết mọi race condition

Hủy request giúp tiết kiệm công việc, nhưng không phải cách duy nhất để ngăn dữ liệu cũ ghi đè dữ liệu mới. Một response có thể đã hoàn tất ngay trước lúc abort hoặc code xử lý có thể đã bắt đầu chạy.

Với chức năng tìm kiếm, có thể kết hợp abort và sequence number:

```js
let activeSearchController = null;
let searchSequence = 0;

async function search(query) {
  activeSearchController?.abort();

  const controller = new AbortController();
  activeSearchController = controller;
  const sequence = ++searchSequence;

  try {
    const response = await fetch(
      '/api/search?q=' + encodeURIComponent(query),
      { signal: controller.signal }
    );
    if (!response.ok) throw new Error('HTTP ' + response.status);

    const data = await response.json();

    if (sequence !== searchSequence || controller.signal.aborted) {
      return;
    }

    renderSearchResults(data);
  } catch (error) {
    if (!controller.signal.aborted) {
      showSearchError(error);
    }
  } finally {
    if (activeSearchController === controller) {
      activeSearchController = null;
    }
  }
}
```

Sequence number bảo vệ giao diện trước kết quả cũ, còn abort dừng request cũ nếu có thể. Dùng cả hai giúp xử lý trường hợp response vừa hoàn tất hoặc tác vụ hậu xử lý không còn nằm dưới quyền điều khiển trực tiếp của Fetch.

### 7.1. Abort không phải transaction rollback

Khi browser abort một POST request, server có thể đã nhận và xử lý dữ liệu. Việc đóng kết nối không đảm bảo server hoàn tác thay đổi đã thực hiện.

Ví dụ người dùng nhấn “Tạo đơn hàng”, sau đó đóng dialog và client abort request. Server có thể đã tạo đơn trước khi kết nối bị đóng. Nếu người dùng nhấn lại, có nguy cơ tạo đơn trùng.

Với thao tác có side effect:

- Dùng idempotency key hoặc request identifier do client tạo và server kiểm tra.
- Server thực hiện transaction và kiểm tra quyền trước khi commit.
- Có API tra cứu trạng thái tác vụ nếu kết quả có thể không rõ sau khi client mất kết nối.
- Không thông báo “thao tác đã bị rollback” chỉ vì Fetch reject do abort.
- Thiết kế endpoint để retry an toàn hoặc yêu cầu client xác nhận trạng thái trước khi gửi lại.

Abort là cơ chế điều khiển phía client. Muốn hủy công việc server đang chạy, backend phải có giao thức hủy riêng và hợp tác dừng tác vụ.

## 8. Phân biệt abort, timeout, lỗi mạng và HTTP error

Fetch chỉ reject với các lỗi như network failure, CORS failure hoặc abort. HTTP status 404, 401, 429 hay 500 vẫn tạo một Response và Promise Fetch resolve bình thường.

| Tình huống | Hành vi thường gặp | Cách xử lý |
|---|---|---|
| User abort | Promise reject do signal abort | Kiểm tra signal.aborted/reason và bỏ qua thông báo lỗi mạng chung |
| Timeout qua AbortSignal.timeout() | Signal abort với reason tên TimeoutError | Hiển thị thông báo hết thời gian chờ |
| Network failure | Fetch reject, signal có thể chưa abort | Báo lỗi kết nối và quyết định retry |
| CORS failure | Fetch reject, chi tiết thường bị browser giới hạn | Kiểm tra response/header CORS ở server |
| HTTP 4xx/5xx | Fetch resolve với response.ok === false | Đọc status và xử lý theo API contract |
| XHR abort | Phát sự kiện abort, sau đó loadend | Xử lý trong onabort, cleanup listener |
| XHR timeout | Phát sự kiện timeout, sau đó loadend | Xử lý trong ontimeout |

Mẫu xử lý Fetch:

```js
try {
  const response = await fetch('/api/data', { signal });

  if (!response.ok) {
    throw new Error('HTTP ' + response.status);
  }

  return await response.json();
} catch (error) {
  if (signal.aborted) {
    console.log('Canceled:', signal.reason);
  } else {
    throw error;
  }
}
```

Không dùng catch để biến mọi lỗi thành dữ liệu rỗng. Làm vậy có thể che giấu lỗi server, lỗi mạng hoặc lỗi parse JSON và khiến giao diện hiển thị trạng thái sai.

## 9. Chẩn đoán và kiểm thử bằng DevTools

Khi kiểm tra abort:

1. Mở DevTools → Network và bật Preserve log.
2. Gửi một request có độ trễ đủ dài.
3. Hủy request từ giao diện hoặc từ Console bằng controller đang hoạt động.
4. Quan sát request bị đánh dấu canceled/aborted tùy browser.
5. Kiểm tra thời điểm abort: trước response headers, sau headers hay trong lúc body đang tải.
6. So sánh thời gian request, transferred bytes và event log phía server.
7. Với XHR, xem Initiator và các event abort, timeout, loadend.

Tên trạng thái hiển thị trong Network khác nhau giữa browser. Một request có thể đã được server xử lý dù DevTools báo canceled. Network panel chỉ mô tả quan sát từ phía browser.

Các lỗi triển khai thường gặp:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Abort không có tác dụng | Fetch không nhận đúng signal hoặc controller đã bị thay | Kiểm tra signal truyền vào đúng request |
| Request mới bị hủy ngay | Dùng lại controller đã abort | Tạo controller mới cho mỗi lần tác vụ |
| Lỗi abort hiện như lỗi server | catch không phân biệt signal aborted | Kiểm tra signal.aborted và signal.reason |
| Request cũ ghi đè kết quả mới | Chỉ abort mà không kiểm tra thứ tự kết quả | Dùng sequence/request ID trước khi cập nhật UI |
| XHR không vào onabort | Handler gắn sau khi request đã kết thúc hoặc abort nhầm instance | Gắn event handler trước send() và giữ đúng XHR reference |
| Timeout và user cancel bị nhập làm một | Không phân biệt reason | Dùng reason riêng hoặc AbortSignal.any() |
| Server vẫn thực hiện thao tác | Abort phía client không rollback server | Dùng idempotency và cơ chế cancel server-side nếu cần |
| Listener vẫn chạy sau khi rời màn hình | Không gỡ event listener | Dùng signal trong addEventListener hoặc cleanup thủ công |

## 10. Thực hành: lab Abort request với Node.js

Lab tạo hai loại endpoint có độ trễ:

- /api/slow trả JSON sau 8 giây để thử hủy trước response.
- /api/stream gửi nhiều chunk để thử hủy sau khi headers đã tới và trong lúc đọc body.

Trang lab có Fetch, Fetch stream, XMLHttpRequest và timeout. Server ghi log khi client đóng kết nối trước khi response hoàn tất. Dữ liệu trong lab chỉ là chuỗi thử nghiệm, không có credential hoặc dữ liệu người dùng.

### Bước 1 — Tạo file abort-request-lab.cjs

```js
const http = require('node:http');

const page = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>Abort request lab</title></head><body>',
  '<h1>Abort request lab</h1>',
  '<p>Server dùng localhost và chỉ trả dữ liệu giả.</p>',
  '<button id="fetch-start" type="button">Start slow Fetch</button>',
  '<button id="fetch-abort" type="button">Abort Fetch</button>',
  '<button id="stream-start" type="button">Start stream</button>',
  '<button id="stream-abort" type="button">Abort stream</button>',
  '<button id="xhr-start" type="button">Start XHR</button>',
  '<button id="xhr-abort" type="button">Abort XHR</button>',
  '<button id="timeout-start" type="button">Fetch with 2s timeout</button>',
  '<pre id="output"></pre>',
  '<script>',
  "const output = document.querySelector('#output');",
  'let fetchController = null;',
  'let streamController = null;',
  'let xhr = null;',
  "function log(message) { output.textContent += message + '\\n'; }",
  'function describeError(error, signal) {',
  '  if (signal?.aborted) {',
  '    return "aborted: " + (signal.reason?.name || error.name);',
  '  }',
  '  return "error: " + error.name + " - " + error.message;',
  '}',
  "document.querySelector('#fetch-start').addEventListener('click', async () => {",
  '  fetchController?.abort();',
  '  const controller = new AbortController();',
  '  fetchController = controller;',
  '  log("Fetch started");',
  '  try {',
  '    const response = await fetch("/api/slow", { signal: controller.signal });',
  '    const body = await response.json();',
  '    log("Fetch complete: " + JSON.stringify(body));',
  '  } catch (error) {',
  '    log("Fetch " + describeError(error, controller.signal));',
  '  } finally {',
  '    if (fetchController === controller) fetchController = null;',
  '  }',
  '});',
  "document.querySelector('#fetch-abort').addEventListener('click', () => {",
  '  fetchController?.abort();',
  '  log("Abort Fetch requested");',
  '});',
  "document.querySelector('#stream-start').addEventListener('click', async () => {",
  '  streamController?.abort();',
  '  const controller = new AbortController();',
  '  streamController = controller;',
  '  log("Stream started");',
  '  try {',
  '    const response = await fetch("/api/stream", { signal: controller.signal });',
  '    log("Stream headers received: " + response.status);',
  '    const reader = response.body.getReader();',
  '    const decoder = new TextDecoder();',
  '    while (true) {',
  '      const result = await reader.read();',
  '      if (result.done) break;',
  '      log("Chunk: " + decoder.decode(result.value));',
  '    }',
  '    log("Stream complete");',
  '  } catch (error) {',
  '    log("Stream " + describeError(error, controller.signal));',
  '  } finally {',
  '    if (streamController === controller) streamController = null;',
  '  }',
  '});',
  "document.querySelector('#stream-abort').addEventListener('click', () => {",
  '  streamController?.abort();',
  '  log("Abort stream requested");',
  '});',
  "document.querySelector('#xhr-start').addEventListener('click', () => {",
  '  xhr?.abort();',
  '  const current = new XMLHttpRequest();',
  '  xhr = current;',
  '  current.open("GET", "/api/slow");',
  '  current.timeout = 12000;',
  '  current.onload = () => log("XHR load: status=" + current.status + " " + current.responseText);',
  '  current.onerror = () => log("XHR network error");',
  '  current.onabort = () => log("XHR abort event");',
  '  current.ontimeout = () => log("XHR timeout event");',
  '  current.onloadend = () => {',
  '    log("XHR loadend");',
  '    if (xhr === current) xhr = null;',
  '  };',
  '  current.send();',
  '  log("XHR started");',
  '});',
  "document.querySelector('#xhr-abort').addEventListener('click', () => {",
  '  xhr?.abort();',
  '  log("Abort XHR requested");',
  '});',
  "document.querySelector('#timeout-start').addEventListener('click', async () => {",
  '  if (typeof AbortSignal.timeout !== "function") {',
  '    log("AbortSignal.timeout is not supported by this browser");',
  '    return;',
  '  }',
  '  const signal = AbortSignal.timeout(2000);',
  '  log("Fetch with 2s timeout started");',
  '  try {',
  '    const response = await fetch("/api/slow", { signal });',
  '    log("Timeout test response: " + await response.text());',
  '  } catch (error) {',
  '    log("Timeout test " + describeError(error, signal));',
  '  }',
  '});',
  '</script>',
  '</body></html>',
].join('\n');

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');

  if (req.method === 'GET' && url.pathname === '/') {
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    return res.end(page);
  }

  if (req.method === 'GET' && url.pathname === '/api/slow') {
    console.log('Slow request started');
    const timer = setTimeout(() => {
      if (res.destroyed) return;
      res.writeHead(200, {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
      });
      res.end(JSON.stringify({ ok: true, message: 'Slow response completed' }));
      console.log('Slow response completed');
    }, 8000);

    res.on('close', () => {
      if (!res.writableEnded) {
        clearTimeout(timer);
        console.log('Slow response connection closed before completion');
      }
    });
    return;
  }

  if (req.method === 'GET' && url.pathname === '/api/stream') {
    console.log('Stream request started');
    res.writeHead(200, {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store',
      'Transfer-Encoding': 'chunked',
    });

    let count = 0;
    const timer = setInterval(() => {
      if (res.destroyed) {
        clearInterval(timer);
        return;
      }
      count += 1;
      res.write('chunk ' + count + '\n');
      if (count >= 10) {
        clearInterval(timer);
        res.end();
        console.log('Stream response completed');
      }
    }, 700);

    res.on('close', () => {
      if (!res.writableEnded) {
        clearInterval(timer);
        console.log('Stream connection closed before completion');
      }
    });
    return;
  }

  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('Not found');
});

server.listen(3000, 'localhost', () => {
  console.log('Open http://localhost:3000');
});
```

### Bước 2 — Chạy lab

```sh
node abort-request-lab.cjs
```

Mở http://localhost:3000 trong browser. Nếu cổng 3000 đang được sử dụng, đổi cổng trong server và URL trong phần tạo URL của server.

### Bước 3 — Hủy Fetch trước response

1. Nhấn **Start slow Fetch**.
2. Trong vòng 8 giây, nhấn **Abort Fetch**.
3. Giao diện ghi nhận Fetch bị abort; terminal ghi kết nối đóng trước khi response hoàn tất.
4. Thử lại và đợi đủ 8 giây để thấy response hoàn tất bình thường.

### Bước 4 — Hủy trong lúc đọc stream

1. Nhấn **Start stream**.
2. Chờ log Stream headers received.
3. Chờ một vài chunk rồi nhấn **Abort stream**.
4. Quan sát các chunk dừng lại, Fetch/reader báo lỗi do signal abort và terminal ghi kết nối đóng sớm.

Đây là trường hợp response headers đã tới nhưng body chưa tải xong.

### Bước 5 — Hủy XMLHttpRequest

1. Nhấn **Start XHR**.
2. Nhấn **Abort XHR** trước khi server trả response.
3. Quan sát sự kiện abort và loadend.
4. Chạy lại và không hủy để quan sát load.

### Bước 6 — Thử timeout

Nhấn **Fetch with 2s timeout**. Endpoint phản hồi sau 8 giây nên request sẽ bị timeout trước khi hoàn tất trên browser hỗ trợ AbortSignal.timeout(). Nếu browser không hỗ trợ, lab báo rõ thay vì giả định timeout đã chạy.

## 11. Checklist triển khai abort request

- [ ] Mỗi tác vụ hoặc nhóm tác vụ có controller riêng.
- [ ] Tạo controller mới cho mỗi lần request; không tái sử dụng signal đã abort.
- [ ] Truyền đúng signal vào Fetch hoặc nối signal với XHR.
- [ ] Hủy request khi người dùng rời màn hình, đổi query hoặc hủy thao tác.
- [ ] Dùng timeout phù hợp với UX và loại API.
- [ ] Phân biệt AbortError, TimeoutError, network failure và HTTP status.
- [ ] Xử lý trường hợp abort trước headers và trong lúc đọc body.
- [ ] Gỡ event listener, timer và reference khi tác vụ hoàn tất.
- [ ] Kiểm tra request ID/sequence trước khi cập nhật UI để tránh stale response.
- [ ] Không coi abort phía client là rollback của thao tác server.
- [ ] Dùng idempotency key cho thao tác có side effect có thể được retry.
- [ ] Không log token, cookie hoặc dữ liệu nhạy cảm trong quá trình debug.
- [ ] Kiểm thử hành vi trên browser và loại mạng mà sản phẩm hỗ trợ.

## 12. Câu hỏi tự kiểm tra

**1.** AbortController và AbortSignal khác nhau thế nào?  
**Trả lời:** Controller phát tín hiệu qua abort(); signal là đối tượng được truyền cho API để API biết khi nào cần dừng.

**2.** Có thể tái sử dụng signal sau khi abort không?  
**Trả lời:** Không. Signal đã abort giữ trạng thái đó; tạo controller mới cho tác vụ tiếp theo.

**3.** Fetch bị abort trước response headers thì điều gì xảy ra?  
**Trả lời:** Promise từ Fetch reject theo reason của signal và không có response để xử lý.

**4.** Fetch đã resolve có còn bị abort ảnh hưởng không?  
**Trả lời:** Có. Nếu body vẫn đang tải hoặc đang được đọc, việc tiêu thụ body có thể reject khi signal abort.

**5.** AbortSignal.timeout() thường dùng reason nào?  
**Trả lời:** TimeoutError; cần kiểm tra hỗ trợ browser và phân biệt với abort do người dùng.

**6.** AbortSignal.any() dùng để làm gì?  
**Trả lời:** Kết hợp nhiều signal; signal kết quả abort khi một signal đầu vào abort và giữ reason tương ứng.

**7.** XMLHttpRequest hủy request bằng API nào?  
**Trả lời:** Gọi xhr.abort() và xử lý sự kiện abort/loadend.

**8.** Vì sao cần sequence number dù đã gọi abort request cũ?  
**Trả lời:** Response cũ có thể đã hoàn tất hoặc xử lý đã bắt đầu; sequence number ngăn kết quả cũ ghi đè dữ liệu mới.

**9.** Abort POST có bảo đảm server rollback không?  
**Trả lời:** Không. Server có thể đã commit thay đổi; cần idempotency hoặc giao thức hủy phía server.

**10.** HTTP 404 có làm Fetch reject như abort không?  
**Trả lời:** Không. Fetch resolve với Response có status 404; ứng dụng phải kiểm tra response.ok hoặc response.status.

## Tổng kết

Abort request giúp ứng dụng dừng các tác vụ mạng không còn cần thiết. Với Fetch, tạo AbortController, truyền signal và gọi abort từ tương tác hoặc cleanup; dùng timeout và signal kết hợp khi có nhiều điều kiện hủy. Với XMLHttpRequest, gọi xhr.abort() hoặc nối sự kiện abort của signal vào XHR. Hãy xử lý cả giai đoạn chờ headers và đọc body, phân biệt hủy với lỗi mạng/HTTP, quản lý controller theo vòng đời tác vụ và bảo vệ giao diện khỏi stale response. Abort phía client không đảm bảo server dừng hoặc rollback công việc đã nhận; thao tác có side effect vẫn cần idempotency và kiểm soát ở backend.
