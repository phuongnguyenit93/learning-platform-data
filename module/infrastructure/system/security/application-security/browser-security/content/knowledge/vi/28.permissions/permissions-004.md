# Microphone: quyền truy cập micro trong trình duyệt

## 1. Microphone permission là gì?

Microphone permission là quyền mà browser quản lý để một trang web có thể lấy âm thanh từ micro của thiết bị. API phổ biến là `navigator.mediaDevices.getUserMedia()` với cấu hình `audio`. Khi trang yêu cầu quyền, browser có thể hiển thị hộp thoại để người dùng cho phép hoặc từ chối truy cập.

Ví dụ cơ bản:

```js
async function requestMicrophone() {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: true,
    video: false
  });

  return stream;
}
```

Kết quả là một `MediaStream` chứa một hoặc nhiều `MediaStreamTrack`. Ứng dụng có thể xử lý âm thanh, gửi track qua WebRTC hoặc ghi âm bằng MediaRecorder nếu người dùng chủ động bắt đầu chức năng đó.

Quyền microphone nhạy cảm vì âm thanh có thể tiết lộ cuộc trò chuyện, danh tính, môi trường xung quanh và thông tin riêng tư. Vì vậy, browser yêu cầu trang chạy trong secure context, áp dụng permission của người dùng và có thể giới hạn quyền qua Permissions Policy.

**Nguyên tắc:** chỉ yêu cầu microphone khi người dùng bắt đầu một chức năng cần âm thanh; hiển thị rõ trạng thái đang thu, cung cấp thao tác dừng dễ thấy và dừng mọi track khi không còn cần thiết.

Bài viết thuộc chương **Permissions** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Nội dung kết nối microphone permission với secure context, origin, iframe, Permissions Policy, browser permission prompt, quyền riêng tư và vòng đời MediaStream. Những lớp này giúp kiểm soát việc trang web có thể yêu cầu và sử dụng thiết bị; chúng không thay thế xác thực, phân quyền hoặc bảo vệ dữ liệu phía server.

Sau bài học, bạn có thể:

- Giải thích cách `getUserMedia()` yêu cầu microphone permission.
- Phân biệt permission state với trạng thái thực tế của audio track.
- Nhận diện điều kiện secure context và giới hạn khi chạy trong iframe.
- Dùng Permissions API để quan sát trạng thái quyền khi browser hỗ trợ.
- Chọn audio constraints phù hợp và xử lý lỗi thường gặp.
- Dừng track đúng cách khi kết thúc phiên thu âm.
- Thiết kế giao diện minh bạch, xử lý từ chối quyền và bảo vệ dữ liệu âm thanh.
- Kiểm chứng hành vi trên localhost bằng DevTools.

## 2. Điều kiện để trang yêu cầu microphone

### 2.1. Secure context là điều kiện cơ bản

`getUserMedia()` chỉ được cung cấp trong secure context. Trường hợp phổ biến là trang HTTPS có chứng chỉ hợp lệ. Các địa chỉ local như `http://localhost` và loopback như `http://127.0.0.1` thường được browser xem là potentially trustworthy để phát triển.

Một website HTTP thông thường như `http://app.example.com` không thể dựa vào việc người dùng bấm nút để vượt qua yêu cầu secure context. Trong môi trường không an toàn, `navigator.mediaDevices` có thể không tồn tại hoặc lời gọi API không khả dụng tùy browser.

Kiểm tra trước khi hiển thị chức năng:

```js
function canRequestMicrophone() {
  return Boolean(
    window.isSecureContext &&
    navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function"
  );
}

if (!canRequestMicrophone()) {
  console.warn("Microphone cần secure context và getUserMedia support.");
}
```

Không tự xác định secure context chỉ bằng `location.protocol === "https:"` vì cách đó bỏ sót localhost/loopback và không xét ancestor chain của iframe. Dùng `window.isSecureContext` để hỏi browser về tài liệu hiện tại.

### 2.2. Origin của trang có ý nghĩa với permission

Browser gắn quyền với website/origin theo cách triển khai và cài đặt của từng browser. Người dùng thường có thể xem hoặc thay đổi quyền microphone trong Site settings. Quyền đã cấp cho `https://app.example.com` không đồng nghĩa mọi website khác cũng được dùng micro.

Nếu ứng dụng chạy trên nhiều hostname, hãy kiểm thử từng origin thực tế, ví dụ:

- `https://app.example.com`
- `https://staging.example.com`
- `https://preview.example.net`

Không coi staging hoặc subdomain là đáng tin chỉ vì tên gần giống production. Quyền thiết bị phải được đánh giá cho từng origin và từng môi trường triển khai.

### 2.3. Secure context không tự cấp quyền

Một trang HTTPS có thể là secure context nhưng vẫn không lấy được microphone nếu:

- Người dùng từ chối permission.
- Người dùng đã chặn microphone trong cài đặt website.
- Permissions Policy không cho phép tính năng.
- Không có thiết bị microphone phù hợp.
- Hệ điều hành hoặc browser không cấp quyền truy cập thiết bị.
- Thiết bị đang gặp lỗi hoặc bị ứng dụng khác chiếm dụng.

Secure context là điều kiện nền tảng; permission và khả năng sử dụng thiết bị là các điều kiện riêng.

## 3. Yêu cầu microphone bằng getUserMedia

### 3.1. Yêu cầu audio-only

Một ứng dụng chỉ cần microphone nên yêu cầu audio và tắt video:

```js
const stream = await navigator.mediaDevices.getUserMedia({
  audio: true,
  video: false
});
```

Không yêu cầu camera nếu tính năng không cần hình ảnh. Quyền truy cập thiết bị nên có phạm vi tối thiểu để người dùng hiểu ứng dụng đang xin gì.

`getUserMedia()` trả về Promise. Promise chỉ hoàn tất khi browser xử lý yêu cầu; người dùng có thể mất thời gian cân nhắc hoặc không phản hồi hộp thoại. Không khóa toàn bộ giao diện trong lúc chờ.

### 3.2. Chỉ yêu cầu sau hành động rõ ràng

Mẫu giao diện tốt là người dùng bấm nút **Bật micro** sau khi đã đọc mô tả ngắn về mục đích:

```js
const startButton = document.querySelector("#start-mic");
const status = document.querySelector("#status");

startButton.addEventListener("click", async () => {
  status.textContent = "Đang chờ quyền microphone...";

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: false
    });

    status.textContent = "Microphone đang hoạt động.";
    // Lưu stream để quản lý và dừng đúng lúc.
  } catch (error) {
    status.textContent = "Không thể bật microphone: " + error.name;
  }
});
```

Gọi API sau thao tác của người dùng giúp permission prompt có ngữ cảnh rõ ràng. Không nên tự động yêu cầu microphone ngay khi trang vừa tải, khi người dùng chỉ mở trang để đọc hoặc khi chức năng chưa được giải thích.

Không phải mọi browser đều yêu cầu transient user activation theo cùng một quy tắc cho `getUserMedia()`. Tuy vậy, một nút hành động rõ ràng vẫn là thiết kế UX và quyền riêng tư tốt.

### 3.3. Permission prompt

Browser có thể hiển thị prompt hỏi người dùng có cho phép trang sử dụng microphone không. Giao diện prompt, cách lưu lựa chọn và thời hạn permission khác nhau theo browser, hệ điều hành, chế độ riêng tư và cài đặt người dùng.

Ứng dụng không được giả định rằng:

- Prompt chắc chắn xuất hiện mỗi lần gọi.
- Permission đã cấp sẽ tồn tại vĩnh viễn.
- Permission đã từ chối có thể được hỏi lại ngay lập tức.
- Tên thiết bị và danh sách thiết bị luôn hiển thị trước khi cấp quyền.

Nếu người dùng từ chối, hãy giải thích cách họ có thể tự thay đổi quyền trong cài đặt browser khi muốn. Không lặp lời gọi liên tục để gây áp lực hoặc tìm cách né lựa chọn của người dùng.

## 4. Permissions API và trạng thái microphone

### 4.1. Ba trạng thái thường gặp

Permissions API có thể cho biết trạng thái quyền microphone trong browser hỗ trợ descriptor tương ứng:

| State | Ý nghĩa |
|---|---|
| `granted` | Browser cho biết quyền đã được cấp |
| `denied` | Quyền bị từ chối hoặc bị policy/cài đặt chặn |
| `prompt` | Chưa có quyết định cấp quyền được ghi nhận; lần gọi API có thể cần xử lý prompt |

`prompt` không đảm bảo browser sẽ hiển thị prompt trong mọi trường hợp. Một policy, cài đặt thiết bị hoặc trạng thái document vẫn có thể khiến request thất bại.

### 4.2. Truy vấn permission state

Có thể thử truy vấn:

```js
async function readMicrophonePermission() {
  if (!navigator.permissions?.query) {
    return "unsupported";
  }

  try {
    const result = await navigator.permissions.query({
      name: "microphone"
    });

    return result.state;
  } catch (error) {
    // Browser có thể chưa hỗ trợ microphone descriptor.
    return "unsupported";
  }
}

console.log(await readMicrophonePermission());
```

Hỗ trợ descriptor `microphone` của Permissions API không đồng đều giữa các browser. Hãy xử lý lỗi và coi đây là thông tin bổ sung. `getUserMedia()` mới là API thực hiện yêu cầu lấy stream; truy vấn permission không mở micro và không tự hiển thị prompt.

### 4.3. Theo dõi thay đổi trạng thái

Nếu browser hỗ trợ truy vấn, đối tượng PermissionStatus có thể phát sự kiện khi state thay đổi:

```js
async function watchMicrophonePermission() {
  if (!navigator.permissions?.query) return;

  try {
    const permission = await navigator.permissions.query({
      name: "microphone"
    });

    const update = () => {
      console.log("Microphone permission:", permission.state);
    };

    permission.addEventListener("change", update);
    update();
  } catch {
    console.log("Không thể theo dõi microphone permission trên browser này.");
  }
}
```

Ứng dụng vẫn phải quản lý track đang chạy riêng. Thay đổi permission state và trạng thái stream không phải cùng một tín hiệu; browser có thể thay đổi quyền, thiết bị có thể ngắt kết nối hoặc track có thể kết thúc vì nguyên nhân khác.

### 4.4. Không dùng permission state làm bằng chứng duy nhất

Một state là `granted` không chứng minh:

- Microphone đang thu âm.
- Có audio track đang sống.
- Thiết bị không bị ngắt kết nối.
- Người dùng đã đồng ý với mọi mục đích xử lý dữ liệu của ứng dụng.
- Ứng dụng được phép tải âm thanh lên server.

Hãy kiểm tra stream, track và luồng xử lý thực tế. Permission chỉ trả lời câu hỏi browser có cho phép truy cập tính năng hay không.

## 5. Permissions Policy và microphone trong iframe

### 5.1. Chính sách mặc định

Microphone là một feature có thể được kiểm soát bằng **Permissions Policy**. Chính sách này giới hạn document/origin nào được phép sử dụng microphone.

Một response header có thể chỉ cho phép chính origin của trang:

```http
Permissions-Policy: microphone=(self)
```

Hoặc chặn hoàn toàn microphone:

```http
Permissions-Policy: microphone=()
```

Nếu policy không cho phép document sử dụng microphone, browser có thể từ chối yêu cầu ngay cả khi người dùng trước đó đã cấp permission ở cấp browser.

### 5.2. Iframe cùng origin

Theo mặc định, allowlist của microphone thường là `self`. Iframe cùng origin có thể được hưởng policy cho phép từ parent, nhưng vẫn chịu các hạn chế sandbox, policy kế thừa và permission của browser.

Ví dụ:

```html
<iframe
  src="/voice-widget"
  title="Voice widget">
</iframe>
```

Đừng suy luận chỉ từ việc iframe cùng origin rằng microphone chắc chắn hoạt động. Kiểm tra response header, thuộc tính iframe, secure context bên trong frame và permission state.

### 5.3. Iframe cross-origin cần delegation

Nếu widget ở origin khác cần microphone, parent có thể cấp quyền rõ ràng qua Permissions Policy header và thuộc tính `allow`:

```http
Permissions-Policy: microphone=(self "https://voice.example.net")
```

```html
<iframe
  src="https://voice.example.net/recorder"
  allow="microphone"
  title="Voice recorder">
</iframe>
```

Các điều kiện cần cùng thỏa mãn:

1. Parent policy cho phép origin widget sử dụng microphone.
2. Iframe delegation không loại bỏ quyền đó.
3. Child là secure context.
4. Browser và hệ điều hành hỗ trợ thiết bị.
5. Người dùng cấp permission theo prompt/cài đặt của browser.

Thuộc tính `allow` không thể nới lỏng một response policy đã cấm microphone. Quyền trong iframe là kết quả của các policy giao nhau từ ancestor tới child.

### 5.4. Không cấp microphone cho mọi frame

Tránh cấu hình rộng nếu chỉ một widget cần thu âm. Không dùng `microphone=(*)` trừ khi có lý do đặc biệt và đánh giá rủi ro rõ ràng. Hãy chỉ định origin cụ thể, giới hạn số frame được nhúng và review nơi nội dung frame được phục vụ.

Nếu nội dung không tin cậy, hãy cân nhắc origin riêng, sandbox và không cấp quyền microphone. Việc cho phép script chạy trong iframe không tự động có nghĩa phải cho phép thiết bị.

## 6. Audio constraints và lựa chọn thiết bị

### 6.1. Constraints là yêu cầu hoặc ưu tiên

`getUserMedia()` cho phép mô tả chất lượng và loại audio mong muốn:

```js
const stream = await navigator.mediaDevices.getUserMedia({
  audio: {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    channelCount: 1
  },
  video: false
});
```

Các thuộc tính như echo cancellation, noise suppression và auto gain control có thể giúp trải nghiệm gọi thoại. Browser có thể không hỗ trợ tất cả hoặc không đáp ứng chính xác mọi yêu cầu.

### 6.2. Ideal và exact

Constraint có thể biểu diễn một giá trị ưu tiên hoặc bắt buộc:

```js
const stream = await navigator.mediaDevices.getUserMedia({
  audio: {
    channelCount: { ideal: 1 },
    sampleRate: { ideal: 48000 },
    echoCancellation: { ideal: true }
  },
  video: false
});
```

`ideal` là ưu tiên; browser có thể chọn cấu hình gần phù hợp. `exact` yêu cầu giá trị cụ thể; nếu không thể đáp ứng, Promise có thể reject với `OverconstrainedError`.

Đừng đặt nhiều `exact` không cần thiết. Ràng buộc quá chặt làm giảm khả năng hoạt động trên các thiết bị khác nhau và có thể tạo thêm thông tin về khả năng thiết bị trước khi người dùng cấp quyền.

### 6.3. Chọn microphone theo deviceId

Sau khi có permission hoặc trong điều kiện browser cho phép liệt kê thiết bị, ứng dụng có thể lấy danh sách:

```js
const devices = await navigator.mediaDevices.enumerateDevices();

const microphones = devices.filter((device) => {
  return device.kind === "audioinput";
});

console.table(
  microphones.map((device) => ({
    label: device.label || "Microphone",
    deviceId: device.deviceId
  }))
);
```

Trước khi permission được cấp, browser có thể ẩn label hoặc giới hạn thông tin thiết bị. Không giả định label luôn có sẵn. Cần tránh ghi deviceId hoặc danh sách thiết bị vào log không cần thiết.

Có thể yêu cầu một thiết bị cụ thể:

```js
const stream = await navigator.mediaDevices.getUserMedia({
  audio: {
    deviceId: { exact: selectedDeviceId }
  },
  video: false
});
```

Nếu thiết bị bị rút ra hoặc ID không còn hợp lệ, request có thể thất bại. Hãy cung cấp lựa chọn quay lại microphone mặc định.

### 6.4. Kiểm tra settings và capabilities

Sau khi có track, có thể xem cấu hình thực tế:

```js
const track = stream.getAudioTracks()[0];

console.log("Settings:", track.getSettings());

if (typeof track.getCapabilities === "function") {
  console.log("Capabilities:", track.getCapabilities());
}
```

`getSettings()` phản ánh cấu hình đang dùng. `getCapabilities()` cho biết các khả năng browser công bố cho track. Không phải browser/thiết bị nào cũng trả cùng tập field.

## 7. Vòng đời MediaStream và audio track

### 7.1. Permission và stream là hai thứ khác nhau

Khi `getUserMedia()` thành công, ứng dụng nhận một stream. Stream có thể chứa audio track với trạng thái riêng:

- `readyState === "live"`: track còn hoạt động.
- `readyState === "ended"`: track đã kết thúc.
- `muted`: nguồn tạm thời không cung cấp dữ liệu.
- `enabled`: ứng dụng có bật track để phát dữ liệu hay không.

Người dùng có thể giữ permission ở cấp browser nhưng ứng dụng vẫn chưa có stream. Ngược lại, stream đã tạo cần được dừng rõ ràng khi chức năng kết thúc.

### 7.2. Dừng microphone đúng cách

Gọi `stop()` trên mọi track để kết thúc việc sử dụng stream:

```js
function stopStream(stream) {
  if (!stream) return;

  for (const track of stream.getTracks()) {
    track.stop();
  }
}
```

Khi ứng dụng không cần microphone nữa, hãy:

1. Dừng mọi track trong stream.
2. Xóa tham chiếu stream khỏi trạng thái ứng dụng.
3. Gỡ stream khỏi phần tử audio/video nếu đã gán `srcObject`.
4. Cập nhật giao diện để người dùng biết microphone đã dừng.

Không dựa vào garbage collection để giải phóng microphone. Một tham chiếu còn sót hoặc component chưa unmount đúng có thể giữ track hoạt động lâu hơn dự kiến.

### 7.3. Theo dõi track event

Track có thể bị mute/unmute hoặc kết thúc do thiết bị, browser hay hệ điều hành:

```js
const [track] = stream.getAudioTracks();

track.addEventListener("mute", () => {
  console.log("Audio source tạm thời không có dữ liệu.");
});

track.addEventListener("unmute", () => {
  console.log("Audio source hoạt động trở lại.");
});

track.addEventListener("ended", () => {
  console.log("Audio track đã kết thúc.");
});
```

Sự kiện `mute` không nhất thiết có nghĩa người dùng đã thu hồi permission. Nó có thể phản ánh thiết bị tạm thời không cung cấp dữ liệu. Khi track kết thúc, hãy cập nhật trạng thái UI và cho phép người dùng chủ động thử lại nếu phù hợp.

Gọi `track.stop()` sẽ đặt track về trạng thái ended; ứng dụng nên tự cập nhật giao diện trong hàm dừng thay vì chờ sự kiện ended từ chính lời gọi stop.

### 7.4. enabled và stop khác nhau

`track.enabled = false` làm track không phát dữ liệu âm thanh hữu ích, thường được dùng cho nút mute trong cuộc gọi. Track vẫn còn sống và thiết bị có thể vẫn đang được giữ bởi capture session.

`track.stop()` kết thúc track và giải phóng việc sử dụng nguồn tương ứng khi không còn track nào khác giữ nguồn. Nếu người dùng bấm **Tắt micro**, hãy dừng track khi mục tiêu là kết thúc capture. Nếu chỉ cần tạm mute trong cuộc gọi, có thể dùng enabled nhưng phải hiển thị trạng thái rõ ràng.

## 8. Xử lý lỗi getUserMedia

Lời gọi có thể reject với các DOMException khác nhau. Không nên hiển thị nguyên văn stack trace hoặc thông tin nội bộ cho người dùng.

| Error name | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `NotAllowedError` | Người dùng từ chối, cài đặt browser/OS hoặc Permissions Policy không cho phép | Giải thích cách kiểm tra site settings/policy; không lặp prompt |
| `NotFoundError` | Không có thiết bị phù hợp với yêu cầu | Báo không tìm thấy microphone và cho chọn thiết bị khác |
| `NotReadableError` | Thiết bị hoặc hệ điều hành không thể mở nguồn âm thanh | Kiểm tra quyền OS, ứng dụng khác đang dùng thiết bị và kết nối phần cứng |
| `OverconstrainedError` | Constraint bắt buộc không được đáp ứng | Nới constraint, ưu tiên ideal thay vì exact |
| `AbortError` | Quá trình bắt đầu capture bị hủy bởi lỗi hệ thống/browser | Cho phép thử lại sau khi kiểm tra thiết bị |
| `InvalidStateError` | Document không ở trạng thái active phù hợp | Chỉ yêu cầu từ trang đang hoạt động |
| `TypeError` | Constraints không hợp lệ hoặc API không khả dụng trong môi trường hiện tại | Kiểm tra cấu hình và secure context |

Tên lỗi và cách browser ánh xạ nguyên nhân có thể khác theo implementation. Ví dụ, việc từ chối permission, policy chặn hoặc cài đặt riêng tư có thể cùng biểu hiện thành `NotAllowedError`. Trong insecure context, `navigator.mediaDevices` thường không được expose; ứng dụng nên kiểm tra secure context và API availability trước khi gọi.

Mẫu xử lý:

```js
async function acquireAudio() {
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: false
    });
  } catch (error) {
    switch (error.name) {
      case "NotAllowedError":
        showMessage("Microphone chưa được cấp quyền.");
        break;
      case "NotFoundError":
        showMessage("Không tìm thấy microphone phù hợp.");
        break;
      case "NotReadableError":
        showMessage("Không thể mở microphone. Hãy kiểm tra thiết bị.");
        break;
      case "OverconstrainedError":
        showMessage("Cấu hình audio không phù hợp với thiết bị.");
        break;
      default:
        showMessage("Không thể khởi động microphone.");
    }

    console.error("Microphone request failed:", error.name);
    return null;
  }
}
```

Chỉ log tên lỗi hoặc thông tin kỹ thuật cần thiết. Không ghi âm thanh, transcript, tên thiết bị hay nội dung cuộc trò chuyện vào telemetry mặc định.

## 9. Ghi âm và xử lý dữ liệu audio

### 9.1. MediaRecorder là bước riêng

Có stream microphone không có nghĩa ứng dụng phải ghi âm. Nếu sản phẩm cần ghi âm, hãy giải thích mục đích, thời lượng, nơi lưu và ai có thể truy cập trước khi bắt đầu.

Ví dụ dùng MediaRecorder sau khi người dùng bấm **Bắt đầu ghi**:

```js
function createRecorder(stream) {
  if (!window.MediaRecorder) {
    throw new Error("Browser không hỗ trợ MediaRecorder");
  }

  const chunks = [];
  const recorder = new MediaRecorder(stream);

  recorder.addEventListener("dataavailable", (event) => {
    if (event.data.size > 0) {
      chunks.push(event.data);
    }
  });

  recorder.addEventListener("stop", () => {
    const blob = new Blob(chunks, {
      type: recorder.mimeType || "audio/webm"
    });

    // Chuyển blob tới luồng lưu trữ đã được người dùng đồng ý.
    console.log("Recording size:", blob.size);
  });

  return recorder;
}
```

Bắt đầu và dừng recording bằng hành động rõ ràng:

```js
const recorder = createRecorder(stream);

// Chỉ gọi khi người dùng bấm nút ghi.
recorder.start();

// Khi người dùng bấm dừng.
recorder.stop();
```

Dừng MediaRecorder không tự thay thế việc dừng microphone track. Sau khi kết thúc phiên, hãy dừng recorder nếu đang chạy và dừng mọi track trong stream.

### 9.2. Chọn MIME type có hỗ trợ

Khả năng ghi và định dạng phụ thuộc browser:

```js
const candidates = [
  "audio/webm;codecs=opus",
  "audio/ogg;codecs=opus",
  "audio/mp4"
];

const mimeType = candidates.find((type) => {
  return MediaRecorder.isTypeSupported(type);
});

const recorder = mimeType
  ? new MediaRecorder(stream, { mimeType })
  : new MediaRecorder(stream);
```

Không giả định mọi browser tạo cùng định dạng hoặc chất lượng. Nếu ứng dụng cần upload, server phải xác thực loại file, kích thước, thời lượng và xử lý dữ liệu như nội dung không tin cậy.

### 9.3. Bảo vệ audio trên đường truyền và khi lưu

Âm thanh là dữ liệu cá nhân. Khi truyền lên server:

- Dùng HTTPS.
- Xác thực người dùng và kiểm tra quyền truy cập recording.
- Giới hạn dung lượng, thời lượng và loại nội dung.
- Kiểm tra quyền sở hữu trước khi phát hoặc tải recording.
- Đặt thời hạn lưu và hỗ trợ xóa theo chính sách sản phẩm.
- Không dùng URL đoán được làm cơ chế phân quyền.
- Không ghi blob, audio chunk hoặc transcript vào log không cần thiết.

Nếu gửi audio qua WebRTC, cần cấu hình signaling, danh tính peer và quyền tham gia phiên phù hợp. Mã hóa transport không thay thế việc xác thực người tham gia và bảo vệ dữ liệu ghi lại.

## 10. Quyền riêng tư và thiết kế giao diện

### 10.1. Giải thích trước khi xin quyền

Trước khi gọi API, giao diện nên nói rõ:

- Microphone được dùng cho chức năng nào.
- Âm thanh có được truyền tới server hay chỉ xử lý trên thiết bị.
- Khi nào việc thu âm bắt đầu và kết thúc.
- Dữ liệu có được lưu hay không và lưu trong bao lâu.
- Cách người dùng tắt microphone hoặc rời phiên.

Tránh dùng nút chung chung như **Tiếp tục** để xin quyền thiết bị mà không nêu mục đích.

### 10.2. Hiển thị trạng thái capture

Khi track đang hoạt động, hãy hiển thị chỉ báo rõ ràng như **Microphone đang bật** cùng nút **Tắt micro**. Browser và hệ điều hành thường cũng có chỉ báo riêng, nhưng giao diện ứng dụng vẫn cần cho người dùng biết trạng thái trong sản phẩm.

Không che giấu việc capture đang chạy trong tab nền. Nếu sản phẩm cho phép capture khi chuyển tab, giải thích hành vi đó và cung cấp cách dừng dễ truy cập.

### 10.3. Không coi permission là đồng ý cho mọi mục đích

Người dùng cấp quyền microphone cho browser không đồng nghĩa họ đồng ý:

- Ghi âm liên tục.
- Tải toàn bộ âm thanh lên server.
- Chia sẻ recording với người khác.
- Dùng audio cho phân tích hoặc huấn luyện.
- Lưu vô thời hạn.

Permission API chỉ kiểm soát khả năng truy cập thiết bị. Sự đồng ý đối với mục đích xử lý dữ liệu cần được thiết kế và quản lý riêng theo yêu cầu sản phẩm và pháp luật áp dụng.

### 10.4. Không cố vượt lựa chọn của người dùng

Nếu người dùng từ chối hoặc thu hồi quyền:

- Dừng luồng đang hoạt động nếu track đã kết thúc hoặc không còn được phép.
- Hiển thị trạng thái và cách mở site settings khi người dùng muốn thử lại.
- Cung cấp đường dùng sản phẩm không cần microphone nếu có.
- Không tự động gọi lại API theo chu kỳ.
- Không dùng một iframe hoặc origin khác để né quyết định từ chối.

## 11. Phân biệt microphone permission với các cơ chế bảo mật khác

| Cơ chế | Câu hỏi được giải quyết |
|---|---|
| Secure context | Tài liệu có đủ trustworthy để dùng getUserMedia không? |
| Microphone permission | Browser/người dùng có cho trang truy cập thiết bị không? |
| Permissions Policy | Document hoặc iframe có được phép sử dụng microphone không? |
| SOP | Script có được đọc DOM/dữ liệu của origin khác không? |
| CORS | JavaScript có được đọc response cross-origin không? |
| CSP | Tài liệu được tải và thực thi loại nội dung nào? |
| Authentication | Ai đang sử dụng ứng dụng? |
| Authorization | Người dùng có quyền tham gia phiên hoặc đọc recording không? |
| CSRF protection | Request cookie-authenticated thay đổi trạng thái có được xác thực nguồn hợp lệ không? |

CORS không cấp microphone permission. HTTPS không tự động cho phép capture. SOP không thay thế kiểm soát thiết bị. Browser permission cũng không thay thế authorization ở server.

Nếu ứng dụng gửi âm thanh lên endpoint, server vẫn cần xác thực người dùng, kiểm tra quyền của phiên, giới hạn dữ liệu và bảo vệ request thay đổi trạng thái.

## 12. Lab local: yêu cầu và dừng microphone

Lab dưới đây tạo một trang đơn giản. Người học bấm nút để yêu cầu microphone, xem permission state nếu browser hỗ trợ, kiểm tra track và dừng capture.

### 12.1. Tạo file mic-permission-lab.html

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Microphone permission lab</title>
</head>
<body>
  <h1>Microphone permission lab</h1>
  <p id="secure"></p>
  <p id="permission">Permission: chưa kiểm tra</p>
  <p id="status" aria-live="polite">Microphone đang tắt.</p>

  <button id="check">Kiểm tra permission</button>
  <button id="start">Bật microphone</button>
  <button id="stop" disabled>Tắt microphone</button>

  <pre id="details"></pre>

  <script>
    let activeStream = null;

    const secureOutput = document.getElementById("secure");
    const permissionOutput = document.getElementById("permission");
    const statusOutput = document.getElementById("status");
    const detailsOutput = document.getElementById("details");
    const startButton = document.getElementById("start");
    const stopButton = document.getElementById("stop");

    secureOutput.textContent =
      "Secure context: " + window.isSecureContext;

    async function checkPermission() {
      if (!navigator.permissions?.query) {
        permissionOutput.textContent =
          "Permission API không được hỗ trợ.";
        return;
      }

      try {
        const result = await navigator.permissions.query({
          name: "microphone"
        });
        permissionOutput.textContent =
          "Microphone permission: " + result.state;
      } catch {
        permissionOutput.textContent =
          "Browser không hỗ trợ microphone permission query.";
      }
    }

    startButton.addEventListener("click", async () => {
      if (!window.isSecureContext ||
          !navigator.mediaDevices?.getUserMedia) {
        statusOutput.textContent =
          "Cần secure context và getUserMedia support.";
        return;
      }

      startButton.disabled = true;
      statusOutput.textContent =
        "Đang chờ browser xử lý quyền microphone.";

      try {
        activeStream = await navigator.mediaDevices.getUserMedia({
          audio: true,
          video: false
        });

        const tracks = activeStream.getAudioTracks();
        detailsOutput.textContent = tracks.map((track, index) => {
          const settings = track.getSettings();
          return [
            "Track " + index,
            "label: " + (track.label || "Microphone"),
            "state: " + track.readyState,
            "enabled: " + track.enabled,
            "muted: " + track.muted,
            "settings: " + JSON.stringify(settings)
          ].join("\n");
        }).join("\n\n");

        statusOutput.textContent =
          "Microphone đang hoạt động. Bấm Tắt microphone khi hoàn tất.";
        stopButton.disabled = false;

        for (const track of tracks) {
          track.addEventListener("ended", () => {
            statusOutput.textContent =
              "Audio track đã kết thúc.";
            stopButton.disabled = true;
            startButton.disabled = false;
          });
        }

        await checkPermission();
      } catch (error) {
        statusOutput.textContent =
          "Không thể bật microphone: " + error.name;
        detailsOutput.textContent =
          "Kiểm tra site settings, Permissions Policy và thiết bị.";
        startButton.disabled = false;
        await checkPermission();
      }
    });

    stopButton.addEventListener("click", () => {
      if (activeStream) {
        for (const track of activeStream.getTracks()) {
          track.stop();
        }
        activeStream = null;
      }

      detailsOutput.textContent = "";
      statusOutput.textContent = "Microphone đã tắt.";
      stopButton.disabled = true;
      startButton.disabled = false;
    });

    document.getElementById("check").addEventListener(
      "click",
      checkPermission
    );

    window.addEventListener("pagehide", () => {
      if (activeStream) {
        for (const track of activeStream.getTracks()) {
          track.stop();
        }
        activeStream = null;
      }
    });
  </script>
</body>
</html>
```

### 12.2. Chạy qua localhost

Lưu file trong thư mục làm việc và phục vụ bằng static server local. Ví dụ nếu đã có Node.js, tạo file `mic-lab-server.mjs`:

```js
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";

const html = await readFile(
  new URL("./mic-permission-lab.html", import.meta.url)
);

createServer((req, res) => {
  if (req.url !== "/" && req.url !== "/index.html") {
    res.writeHead(404).end("Not found");
    return;
  }

  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(html);
}).listen(8080, "127.0.0.1", () => {
  console.log("Open http://127.0.0.1:8080");
});
```

Chạy:

```bash
node mic-lab-server.mjs
```

Mở `http://127.0.0.1:8080`. Loopback thường được browser xem là potentially trustworthy, nên có thể dùng để thử API yêu cầu secure context.

### 12.3. Các bước kiểm chứng

1. Mở trang và quan sát `Secure context`.
2. Bấm **Kiểm tra permission**; browser có thể trả `granted`, `denied`, `prompt` hoặc báo descriptor không hỗ trợ.
3. Bấm **Bật microphone**; nếu chưa có quyết định, browser có thể hiển thị prompt.
4. Cho phép truy cập và kiểm tra trạng thái track trong phần chi tiết.
5. Mở DevTools để xem Console và quyền microphone của site.
6. Bấm **Tắt microphone**; kiểm tra track đã chuyển sang `ended` và chỉ báo thiết bị của browser đã dừng.
7. Thử từ chối permission hoặc thu hồi quyền trong Site settings, sau đó tải lại và kiểm tra cách ứng dụng xử lý.
8. Thử mở trang bằng HTTP trên một hostname LAN trong môi trường test để so sánh với localhost; API có thể không khả dụng vì không phải secure context.
9. Nếu nhúng trang vào iframe cross-origin, cấu hình Permissions Policy phù hợp và kiểm tra cả response header lẫn thuộc tính `allow`.

Lab không ghi âm, không upload audio và không gửi dữ liệu tới server bên ngoài. Chỉ cấp quyền cho trang local khi bạn chủ động thử nghiệm.

## 13. Checklist review microphone

Trước khi phát hành tính năng dùng microphone, hãy kiểm tra:

1. **Mục đích:** Tính năng có thật sự cần microphone không?
2. **UX:** Người dùng có bấm hành động rõ ràng sau khi được giải thích mục đích không?
3. **Secure context:** Trang có HTTPS hợp lệ hoặc môi trường local được browser tin cậy không?
4. **Origin:** Permission được yêu cầu từ đúng origin dự kiến không?
5. **Iframe:** Nếu chạy trong frame, Permissions Policy và thuộc tính allow đã cấp đúng origin chưa?
6. **Constraints:** Chỉ yêu cầu audio và những constraint thực sự cần thiết chưa?
7. **Permission state:** Có xử lý trường hợp Permissions API không hỗ trợ hoặc query thất bại không?
8. **Errors:** Có phân biệt từ chối quyền, không có thiết bị và lỗi phần cứng không?
9. **Track lifecycle:** Mọi đường rời trang, kết thúc phiên và thao tác tắt đều dừng track chưa?
10. **Indicator:** UI có chỉ báo microphone đang bật và nút tắt dễ tìm không?
11. **Recording:** Việc ghi âm có hành động bắt đầu/dừng và thông báo rõ ràng không?
12. **Data handling:** Audio có HTTPS, authorization, giới hạn lưu trữ và quyền xóa phù hợp không?
13. **Logging:** Log có tránh ghi audio, transcript, device label và dữ liệu nhạy cảm không?
14. **Fallback:** Sản phẩm có hoạt động ở chế độ không microphone nếu người dùng từ chối không?
15. **Testing:** Đã thử trên browser, hệ điều hành, thiết bị và trạng thái permission khác nhau chưa?

## 14. Những hiểu lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
|---|---|
| "HTTPS là có thể dùng micro ngay." | Secure context chỉ là điều kiện; người dùng và policy vẫn quyết định permission. |
| "localhost HTTP không bao giờ là secure." | Localhost và loopback thường được xem là potentially trustworthy. |
| "Permissions API query sẽ mở prompt." | Query chỉ quan sát trạng thái; getUserMedia mới yêu cầu stream. |
| "granted nghĩa là microphone đang thu." | Permission state không chứng minh track đang live. |
| "Người dùng cấp quyền là đồng ý ghi âm." | Quyền truy cập thiết bị không thay thế sự đồng ý cho từng mục đích xử lý dữ liệu. |
| "Bấm mute là đã giải phóng microphone." | enabled=false thường chỉ tắt dữ liệu track; stop() kết thúc track. |
| "Dừng MediaRecorder là đủ." | Cần dừng cả recorder và các MediaStreamTrack khi kết thúc phiên. |
| "Cùng origin thì iframe luôn được dùng micro." | Permissions Policy, allow, secure context và browser permission vẫn áp dụng. |
| "Thuộc tính allow có thể ghi đè mọi policy." | Delegation không thể nới lỏng response policy của ancestor đã cấm feature. |
| "Không có microphone thì chỉ cần retry." | Cần kiểm tra thiết bị, OS permission, constraint và trạng thái browser. |
| "CORS cấp quyền microphone." | CORS điều khiển đọc response cross-origin; microphone là quyền thiết bị riêng. |
| "Audio local không cần bảo vệ." | Dữ liệu audio vẫn có thể chứa thông tin cá nhân và cần được xử lý an toàn. |

## 15. Câu hỏi ôn tập

1. API nào thường được dùng để yêu cầu microphone trong browser?
2. Vì sao getUserMedia yêu cầu secure context?
3. Vì sao localhost HTTP có thể dùng được microphone trong khi website HTTP thông thường không thể?
4. Permissions API query microphone có tự hiển thị prompt không?
5. Ba trạng thái granted, denied và prompt có ý nghĩa gì?
6. Vì sao permission state granted không chứng minh audio track đang hoạt động?
7. Permissions Policy microphone kiểm soát điều gì trong iframe?
8. Làm thế nào cấp microphone cho iframe cross-origin?
9. Sự khác nhau giữa ideal và exact constraint là gì?
10. Khi nào getUserMedia có thể trả NotAllowedError hoặc NotFoundError?
11. Vì sao phải gọi stop() trên mọi MediaStreamTrack khi kết thúc?
12. track.enabled=false khác track.stop() như thế nào?
13. MediaRecorder có tự dừng microphone track không?
14. Vì sao browser permission không đồng nghĩa với sự đồng ý ghi âm hoặc upload?
15. Secure context, Permissions Policy và user permission phối hợp ra sao?

**Đáp án định hướng:** (1) navigator.mediaDevices.getUserMedia(). (2) Microphone là powerful feature có thể thu dữ liệu riêng tư; browser chỉ cho phép trong môi trường trustworthy. (3) Localhost/loopback là ngoại lệ potentially trustworthy cho phát triển. (4) Không; query chỉ đọc state. (5) granted là đã cấp, denied là bị chặn/từ chối, prompt là chưa có quyết định được ghi nhận. (6) Stream có thể chưa được tạo, track đã ended hoặc thiết bị không hoạt động. (7) Nó quyết định document/frame có được phép sử dụng microphone hay không. (8) Parent response policy cho phép origin child và iframe dùng allow="microphone"; các điều kiện secure context và user permission vẫn cần. (9) ideal là ưu tiên, exact là bắt buộc. (10) NotAllowedError thường do permission/policy/context; NotFoundError do không có thiết bị phù hợp. (11) Để kết thúc capture và giải phóng nguồn khi không còn track khác dùng. (12) enabled=false tắt dữ liệu track nhưng track còn live; stop() kết thúc track. (13) Không. (14) Quyền truy cập thiết bị không quyết định mục đích, nơi lưu hoặc chia sẻ dữ liệu. (15) Document phải trustworthy, policy phải cho phép và browser/người dùng phải cấp quyền theo điều kiện tương ứng.

## 16. Tài liệu tham khảo

- [W3C — Media Capture and Streams](https://www.w3.org/TR/mediacapture-streams/): Đặc tả getUserMedia, MediaStream, MediaStreamTrack và constraint.
- [MDN — MediaDevices.getUserMedia()](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia): Cách yêu cầu audio/video và các lỗi thường gặp.
- [MDN — Microphone permissions](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia#privacy_and_security): Điều kiện secure context và quyền riêng tư.
- [MDN — Permissions API](https://developer.mozilla.org/en-US/docs/Web/API/Permissions_API): Truy vấn và theo dõi permission state.
- [MDN — Permissions-Policy: microphone](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/microphone): Kiểm soát microphone feature trong document và iframe.
- [MDN — MediaStreamTrack.stop()](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/stop): Dừng track và kết thúc việc sử dụng nguồn.
- [MDN — MediaRecorder](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder): Ghi dữ liệu từ MediaStream.
- [MDN — MediaDevices.enumerateDevices()](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices): Liệt kê thiết bị media và giới hạn quyền riêng tư.
- [W3C — Permissions Policy](https://www.w3.org/TR/permissions-policy-1/): Mô hình allowlist và delegation tính năng.

**Kết nối với mô hình bảo mật web:** Microphone permission là quyền truy cập thiết bị do browser quản lý. Secure context xác định môi trường có đủ trustworthy để yêu cầu API; Permissions Policy giới hạn frame/origin nào được dùng micro; user permission quyết định browser có cho phép capture. Sau khi nhận stream, ứng dụng phải quản lý track, hiển thị trạng thái, dừng capture và bảo vệ audio như dữ liệu cá nhân. Các cơ chế này phối hợp với origin, CSP, CSRF và authorization nhưng không thay thế lẫn nhau.
