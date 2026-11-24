# Persistent permission: vòng đời và cách quản lý quyền trình duyệt đã cấp

Một website có thể xin quyền dùng vị trí, camera, microphone, thông báo hoặc một số tính năng nhạy cảm khác. Khi người dùng chọn cho phép, trình duyệt có thể lưu quyết định đó để website tiếp tục sử dụng tính năng trong những lần truy cập sau mà không phải hỏi lại mỗi lần.

Quyền được lưu lại thường được gọi là persistent permission (quyền có hiệu lực lâu dài). Tuy nhiên, “persistent” không có nghĩa là quyền tồn tại vĩnh viễn hoặc website được tự do truy cập tài nguyên bất cứ lúc nào. Trình duyệt có thể giới hạn quyền theo origin, profile, loại API, thời gian, trạng thái sử dụng, chính sách hệ thống và quyết định mới của người dùng.

Cần phân biệt ba lớp: trạng thái quyền mà trình duyệt quản lý, khả năng sử dụng API trong ngữ cảnh hiện tại, và quyền ở cấp hệ điều hành hoặc thiết bị. Một trạng thái granted chỉ là một phần trong quá trình kiểm tra.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích persistent permission và vòng đời của một quyết định cấp quyền.
- Phân biệt các trạng thái permission API: prompt, granted và denied.
- Nhận biết quyền được lưu theo origin, profile và loại tính năng.
- Phân biệt quyền lâu dài, quyền một lần, quyền theo phiên và quyền bị tự thu hồi.
- Dùng Permissions API để truy vấn trạng thái và theo dõi thay đổi.
- Gọi API nhạy cảm đúng ngữ cảnh và xử lý trường hợp người dùng từ chối.
- Hiểu cách browser permission phối hợp với Permissions Policy, iframe và quyền hệ điều hành.
- Thiết kế luồng xin quyền có chủ đích, dễ thu hồi và không gây áp lực cho người dùng.
- Kiểm thử quyền sau reload, khởi động lại trình duyệt, đổi profile và thu hồi quyền.

## 1. Persistent permission là gì?

Persistent permission là quyết định cấp quyền được trình duyệt ghi nhớ để một origin có thể tiếp tục yêu cầu sử dụng một tính năng trong các lần truy cập tiếp theo. Ví dụ, người dùng cho phép một ứng dụng bản đồ dùng vị trí. Trong những lần mở lại trang, trình duyệt có thể giữ trạng thái granted và không hiện lại hộp thoại.

Một số trình duyệt có thể cung cấp lựa chọn như:

- Allow once: chỉ cho phép trong một lần hoặc một khoảng thời gian giới hạn.
- Allow while visiting: cho phép trong khi truy cập website hoặc trong phiên hiện tại.
- Always allow: ghi nhớ lựa chọn cho những lần truy cập tiếp theo.
- Ask every time: yêu cầu người dùng quyết định mỗi lần phù hợp.
- Block: từ chối hoặc chặn quyền cho origin.

Tên lựa chọn và cách lưu phụ thuộc trình duyệt, phiên bản, hệ điều hành và loại permission. Không phải API nào cũng có đầy đủ các lựa chọn trên.

### 1.1 Persistent không có nghĩa là vĩnh viễn

Một quyền đã cấp có thể bị thay đổi hoặc hết hiệu lực khi:

- Người dùng thu hồi quyền trong site settings.
- Người dùng thay đổi cài đặt quyền ở cấp trình duyệt.
- Trình duyệt tự động reset quyền của website không được sử dụng trong thời gian dài.
- Quyền một lần hoặc quyền theo phiên hết hạn.
- Người dùng đóng phiên duyệt riêng tư.
- Quản trị viên áp dụng enterprise policy.
- Hệ điều hành thu hồi quyền của ứng dụng trình duyệt đối với camera, microphone hoặc location.
- Trình duyệt thay đổi cách quản lý permission sau một bản cập nhật.
- Origin thay đổi do đổi scheme, hostname hoặc port.

Vì vậy, ứng dụng phải kiểm tra quyền tại thời điểm cần dùng API và luôn xử lý trường hợp quyền không còn khả dụng.

### 1.2 Quyền được gắn với origin

Origin được xác định bởi bộ ba:

~~~text
scheme + hostname + port
~~~

Ví dụ:

| URL | Quan hệ với `https://app.example.test` |
|---|---|
| `https://app.example.test/home` | Cùng origin |
| `https://app.example.test:443/settings` | Cùng origin vì 443 là port mặc định của HTTPS |
| `http://app.example.test` | Khác origin vì scheme khác |
| `https://media.example.test` | Khác origin vì hostname khác |
| `https://app.example.test:8443` | Khác origin vì port khác |

Nếu ứng dụng chuyển từ HTTP sang HTTPS hoặc đổi hostname, quyền đã lưu cho origin cũ không tự động chuyển sang origin mới. Hãy kiểm thử lại permission sau khi đổi domain, subdomain, port hoặc môi trường triển khai.

Một số permission và cơ chế nhúng còn xét đến top-level site hoặc origin đang nhúng. Chi tiết lưu và phân vùng có thể khác giữa các trình duyệt; không giả định một quyết định luôn áp dụng giống nhau trong mọi iframe.

## 2. Permission state: prompt, granted và denied

Permissions API biểu diễn trạng thái quyền bằng ba giá trị chuẩn:

| State | Ý nghĩa | Hành vi ứng dụng nên chuẩn bị |
|---|---|---|
| `granted` | Trình duyệt cho biết quyền hiện đang được cấp | Có thể thử gọi API, nhưng vẫn phải xử lý lỗi từ API hoặc hệ điều hành |
| `denied` | Quyền đang bị từ chối hoặc bị chặn trong ngữ cảnh hiện tại | Giải thích cách người dùng mở site settings để đổi quyền nếu họ muốn |
| `prompt` | Chưa có quyết định cấp quyền áp dụng hoặc trình duyệt có thể cần hỏi | Chỉ gọi API khi người dùng thực hiện hành động có ngữ cảnh rõ ràng |

`prompt` không đồng nghĩa chắc chắn rằng một hộp thoại sẽ xuất hiện. Trình duyệt có thể không hỏi nếu permission bị chặn bởi Permissions Policy, enterprise policy, cài đặt người dùng, yêu cầu secure context hoặc điều kiện riêng của API.

Tương tự, `granted` không bảo đảm API chắc chắn thành công. Thiết bị có thể không tồn tại, hệ điều hành có thể chặn ứng dụng trình duyệt, tài liệu có thể không được phép dùng feature hoặc API có thể thất bại vì lý do khác.

### 2.1 State không nói rõ thời hạn

Permissions API chỉ cung cấp trạng thái hiện tại của permission. Nó không cung cấp một trường chuẩn cho biết:

- Quyền được cấp lúc nào.
- Người dùng chọn Allow once hay Always allow.
- Quyền sẽ hết hạn vào thời điểm nào.
- Quyền được lưu trong profile bao lâu.
- Trình duyệt có kế hoạch tự thu hồi quyền hay không.

Không xây dựng logic dựa trên giả định rằng `granted` đồng nghĩa với quyền vĩnh viễn. Hãy xem state là ảnh chụp hiện tại của quyết định trình duyệt.

## 3. Trình duyệt lưu và thực thi quyền như thế nào?

Trình duyệt thường có một permission store để ghi nhận quyết định của người dùng hoặc chính sách quản trị. Store này thuộc về profile hoặc môi trường duyệt, được trình duyệt dùng khi trang gọi API nhạy cảm.

Một mô hình khái quát:

~~~text
Người dùng mở website
        |
        v
Tài liệu gọi API nhạy cảm
        |
        v
Trình duyệt kiểm tra:
- Secure context?
- Permission state?
- Permissions Policy?
- Context và user activation?
- Điều kiện riêng của API?
        |
        v
Có thể hỏi người dùng nếu cần
        |
        v
Browser permission store ghi nhận quyết định
        |
        v
API tiếp tục hoặc bị từ chối
~~~

Trình duyệt có thể ghi quyết định vào profile để áp dụng trong lần truy cập sau. Khi API được gọi, browser process và các thành phần liên quan kiểm tra quyền trước khi cấp khả năng truy cập thiết bị hoặc tính năng.

Chi tiết nội bộ không giống nhau giữa Chrome, Firefox, Safari và các trình duyệt khác. Điều quan trọng ở phía ứng dụng là không cố đọc permission store hoặc suy đoán cấu trúc lưu trữ của trình duyệt. Hãy dùng API chuẩn và giao diện cài đặt quyền mà trình duyệt cung cấp.

### 3.1 Permission khác với dữ liệu website

Quyết định permission và dữ liệu website là hai loại trạng thái khác nhau. Cookie, localStorage, IndexedDB, Cache Storage và quyền camera có thể được quản lý ở các khu vực cài đặt khác nhau.

Xóa cookie hoặc cache không nhất thiết thu hồi permission. Ngược lại, thu hồi quyền camera không nhất thiết xóa cookie đăng nhập hoặc dữ liệu ứng dụng.

Khi hướng dẫn người dùng reset website, hãy nói rõ họ cần xóa dữ liệu website, thu hồi permission hay cả hai. Các lựa chọn và hành vi cụ thể tùy trình duyệt.

### 3.2 Persistent permission không phải persistent storage

Persistent permission là quyết định cho phép một tính năng như vị trí hoặc camera. Persistent storage là cơ chế riêng của Storage API, có thể được yêu cầu bằng `navigator.storage.persist()` để giảm khả năng dữ liệu origin bị trình duyệt tự động loại bỏ khi thiếu dung lượng.

Hai cơ chế có mục tiêu và vòng đời khác nhau. Gọi `navigator.storage.persist()` không cấp quyền camera, microphone hoặc vị trí; cấp permission cũng không bảo đảm IndexedDB hay Cache Storage được giữ lại khi trình duyệt cần thu hồi dữ liệu.

### 3.3 Profile và chế độ riêng tư

Permission thường được quản lý theo profile trình duyệt. Hai profile khác nhau có thể có quyết định khác nhau cho cùng origin.

Trong chế độ riêng tư hoặc ẩn danh:

- Quyết định có thể chỉ có hiệu lực trong phiên riêng tư.
- Trình duyệt có thể hỏi lại nhiều hơn.
- Một số permission có thể không được cấp hoặc bị giới hạn.
- Khi đóng toàn bộ cửa sổ riêng tư, dữ liệu và quyết định tạm thời có thể bị xóa.

Hành vi cụ thể phụ thuộc trình duyệt. Không dùng chế độ riêng tư làm môi trường duy nhất để xác nhận một permission là persistent.

## 4. Quyền lâu dài, quyền tạm thời và tự thu hồi

Không phải mọi lần người dùng chọn Allow đều tạo ra một quyền lâu dài.

### 4.1 Quyền lâu dài

Với permission được lưu lâu dài, trình duyệt có thể giữ quyết định sau khi tải lại trang hoặc khởi động lại trình duyệt. Ví dụ, người dùng đã cho phép thông báo cho một website và trình duyệt ghi nhớ lựa chọn đó.

Quyền vẫn có thể bị thu hồi thủ công, reset tự động hoặc bị giới hạn bởi chính sách khác.

### 4.2 Quyền một lần hoặc theo phiên

Một số trình duyệt cung cấp lựa chọn chỉ cho phép một lần hoặc trong một phiên. Khi hết thời hạn, trạng thái có thể quay về prompt hoặc trạng thái khác do trình duyệt xác định.

Ứng dụng không có API chung để biết chính xác quyền đang thuộc loại một lần hay lâu dài. Hãy luôn kiểm tra trạng thái trước khi gọi tính năng.

### 4.3 Tự động thu hồi quyền không dùng đến

Một số trình duyệt có cơ chế tự reset permission của website mà người dùng không truy cập trong thời gian dài. Mục tiêu là giảm quyền tồn tại lâu mà không còn cần thiết.

Sau khi quyền bị reset, website có thể thấy trạng thái thay đổi hoặc lần gọi API tiếp theo lại cần người dùng quyết định.

Không nên coi việc người dùng đã cấp quyền trước đây là cam kết rằng lần truy cập sau sẽ tiếp tục được phép.

### 4.4 Permission có thể bị quản trị viên kiểm soát

Trên thiết bị doanh nghiệp, trường học hoặc kiosk, quản trị viên có thể dùng enterprise policy để tự động cấp, từ chối hoặc khóa một số quyền. Người dùng có thể không thay đổi được quyết định đó trong giao diện thông thường.

Ứng dụng nên xử lý trạng thái denied giống nhau về mặt an toàn, bất kể nguồn từ chối là người dùng, trình duyệt hay chính sách quản trị.

## 5. Permissions API dùng để làm gì?

Permissions API cho phép truy vấn trạng thái của một permission và theo dõi khi trạng thái thay đổi.

Ví dụ truy vấn geolocation:

~~~js
async function readGeolocationPermission() {
  if (!navigator.permissions) {
    return { supported: false, state: "unknown" };
  }

  try {
    const status = await navigator.permissions.query({
      name: "geolocation"
    });

    return {
      supported: true,
      state: status.state
    };
  } catch (error) {
    return {
      supported: false,
      state: "unknown",
      error
    };
  }
}

readGeolocationPermission().then(result => {
  console.log(result);
});
~~~

Kết quả `state` là `granted`, `denied` hoặc `prompt`. Ví dụ này không yêu cầu quyền và không làm hộp thoại permission xuất hiện.

### 5.1 Query không phải request

Đây là một điểm dễ nhầm:

- `navigator.permissions.query()` đọc trạng thái permission.
- API cụ thể như `getCurrentPosition()`, `getUserMedia()` hoặc `Notification.requestPermission()` mới thực hiện quy trình xin hoặc sử dụng quyền theo quy tắc của API đó.
- Không có một phương thức `navigator.permissions.request()` chung được hỗ trợ như cách xin mọi loại quyền.

Không gọi query rồi cho người dùng nghĩ rằng họ đã cấp quyền. Hãy dùng nút và nội dung giao diện nói rõ tính năng nào sẽ được sử dụng.

### 5.2 Theo dõi khi permission thay đổi

`PermissionStatus` có sự kiện `change`. Ứng dụng có thể cập nhật giao diện nếu người dùng thu hồi quyền trong lúc trang đang mở:

~~~js
async function watchGeolocationPermission() {
  if (!navigator.permissions) return;

  try {
    const status = await navigator.permissions.query({
      name: "geolocation"
    });

    function renderPermissionState(state) {
      const label = document.querySelector("#location-permission");
      if (label) {
        label.textContent = "Location permission: " + state;
      }
    }

    renderPermissionState(status.state);

    status.addEventListener("change", () => {
      renderPermissionState(status.state);
    });
  } catch (error) {
    console.warn("Permission query is unavailable", error);
  }
}
~~~

Sự kiện này chỉ phản ánh thay đổi mà trình duyệt báo cho PermissionStatus. Ứng dụng vẫn phải bắt lỗi khi gọi API vì trạng thái có thể thay đổi giữa lúc query và lúc sử dụng.

### 5.3 Hỗ trợ permission descriptor không đồng nhất

Không phải mọi trình duyệt đều hỗ trợ truy vấn tất cả permission name hoặc descriptor option. Ví dụ, khả năng query `camera`, `microphone`, `clipboard-read` hoặc các descriptor có thuộc tính bổ sung có thể khác nhau.

Luôn dùng `try/catch`, kiểm tra feature support và có đường xử lý khi query không được hỗ trợ. Không suy ra rằng trình duyệt không hỗ trợ API chỉ vì một permission descriptor cụ thể bị từ chối.

## 6. Xin quyền đúng thời điểm

Ứng dụng nên xin quyền khi người dùng hiểu rõ tính năng và chủ động chọn sử dụng nó.

Một luồng phù hợp:

1. Giải thích tính năng cần quyền gì và dùng vào mục đích nào.
2. Người dùng bấm nút bắt đầu tính năng.
3. Ứng dụng gọi API phù hợp.
4. Trình duyệt hiển thị giao diện quyết định nếu cần.
5. Ứng dụng xử lý kết quả thành công, từ chối hoặc lỗi.
6. Nếu bị từ chối, vẫn cung cấp cách dùng khác nếu có thể.

Không xin camera, microphone, vị trí hoặc thông báo ngay khi trang vừa tải nếu chưa có ngữ cảnh cần thiết.

### 6.1 User activation

Một số permission request hoặc tính năng nhạy cảm chịu quy tắc user activation, tức cần thao tác trực tiếp của người dùng như click hoặc tap. Ngay cả khi API không bắt buộc user activation trong mọi trình duyệt, gọi từ một hành động rõ ràng vẫn giúp người dùng hiểu vì sao hộp thoại xuất hiện và phù hợp với heuristic chống spam của trình duyệt.

Ví dụ yêu cầu notification từ nút:

~~~html
<button id="enable-notifications">
  Bật thông báo
</button>
~~~

~~~js
const button = document.querySelector("#enable-notifications");

button.addEventListener("click", async () => {
  if (!("Notification" in window)) {
    showMessage("Trình duyệt không hỗ trợ thông báo.");
    return;
  }

  try {
    const result = await Notification.requestPermission();

    if (result === "granted") {
      showMessage("Thông báo đã được cho phép.");
    } else if (result === "denied") {
      showMessage("Thông báo đang bị chặn trong cài đặt trình duyệt.");
    } else {
      showMessage("Bạn chưa cấp quyền thông báo.");
    }
  } catch (error) {
    showMessage("Không thể yêu cầu quyền thông báo lúc này.");
  }
});
~~~

Tên hàm `showMessage` trong ví dụ là hàm giao diện do ứng dụng tự định nghĩa. `Notification.requestPermission()` là API riêng của Notifications; không thay nó bằng một lời gọi request chung trên Permissions API.

### 6.2 Không lặp hộp thoại sau khi người dùng từ chối

Nếu người dùng từ chối, không tự động gọi lại API liên tục. Trình duyệt có thể chặn prompt lặp, hiển thị giao diện yên lặng hoặc chuyển permission sang denied.

Hãy giải thích cách người dùng tự mở site settings nếu họ muốn đổi quyết định. Đừng tạo giao diện gây áp lực hoặc giả lập hộp thoại hệ thống.

## 7. Persistent permission với các API thường gặp

### 7.1 Geolocation

Geolocation cho phép website yêu cầu vị trí của thiết bị. Quyền có thể được lưu theo origin, nhưng trình duyệt có thể cung cấp quyền một lần, tạm thời hoặc lâu dài tùy phiên bản.

~~~js
function locateUser() {
  if (!("geolocation" in navigator)) {
    showMessage("Thiết bị hoặc trình duyệt không hỗ trợ vị trí.");
    return;
  }

  navigator.geolocation.getCurrentPosition(
    position => {
      const { latitude, longitude, accuracy } = position.coords;
      showLocation({ latitude, longitude, accuracy });
    },
    error => {
      handleLocationError(error);
    },
    {
      enableHighAccuracy: false,
      timeout: 10000,
      maximumAge: 30000
    }
  );
}
~~~

Một số lưu ý:

- Geolocation yêu cầu secure context trong các trình duyệt hiện đại, thông thường là HTTPS.
- Trình duyệt có thể hỏi người dùng nếu chưa có quyết định.
- `granted` không bảo đảm thiết bị có vị trí chính xác hoặc tín hiệu GPS.
- Người dùng có thể giới hạn độ chính xác hoặc cung cấp vị trí gần đúng.
- `watchPosition()` tạo yêu cầu theo dõi liên tục; hãy dừng bằng `clearWatch()` khi tính năng kết thúc.
- Dừng theo dõi không nhất thiết thu hồi permission đã lưu.

Không giữ theo dõi vị trí sau khi tính năng không còn cần thiết.

### 7.2 Camera và microphone

`getUserMedia()` cho phép yêu cầu stream từ camera hoặc microphone trong secure context và chịu kiểm soát permission của trình duyệt, Permissions Policy và hệ điều hành.

~~~js
async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    showMessage("Camera không khả dụng trong ngữ cảnh hiện tại.");
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: true,
      audio: false
    });

    const video = document.querySelector("#preview");
    video.srcObject = stream;
    await video.play();

    return stream;
  } catch (error) {
    handleMediaError(error);
  }
}
~~~

Khi người dùng kết thúc:

~~~js
function stopMediaStream(stream) {
  if (!stream) return;

  for (const track of stream.getTracks()) {
    track.stop();
  }
}
~~~

Dừng track kết thúc việc sử dụng stream đó. Nó không nhất thiết xóa quyết định permission đã lưu trong trình duyệt.

Ngay cả khi browser permission là granted:

- Hệ điều hành vẫn có thể chặn ứng dụng trình duyệt dùng camera hoặc microphone.
- Thiết bị có thể không được kết nối hoặc đang bị ứng dụng khác sử dụng.
- Permissions Policy có thể cấm tài liệu hiện tại dùng feature.
- Người dùng có thể thay đổi quyền trong khi trang đang mở.
- Trình duyệt vẫn hiển thị chỉ báo khi camera hoặc microphone đang hoạt động.

### 7.3 Notifications

Notifications API có permission state riêng. Website thường cần gọi `Notification.requestPermission()` trong một hành động có chủ đích của người dùng.

Nếu permission đã được lưu là granted, trình duyệt có thể không hỏi lại. Nhưng thông báo vẫn chịu chính sách của trình duyệt, hệ điều hành, chế độ tập trung, cài đặt site và giới hạn của nền tảng.

Quyền thông báo không đồng nghĩa website được phép gửi thông báo bất kỳ lúc nào mà không có giới hạn. Hãy chỉ gửi nội dung có giá trị, đúng ngữ cảnh và tuân thủ lựa chọn của người dùng.

### 7.4 Clipboard

Các thao tác clipboard như đọc dữ liệu thường có kiểm soát chặt hơn thao tác ghi. Chúng có thể phụ thuộc secure context, permission, user activation và chính sách riêng của trình duyệt.

Không giả định một permission state `granted` có thể được dùng để đọc clipboard ở mọi thời điểm. Hãy gọi API trong hành động người dùng phù hợp và xử lý `NotAllowedError` hoặc lỗi tương ứng.

### 7.5 Các API khác

Một số tính năng khác có thể dùng Permission API hoặc cơ chế xin quyền riêng, ví dụ MIDI, Bluetooth, USB, Serial, HID và một số API thiết bị.

Mỗi API có điều kiện riêng về:

- Secure context.
- User activation.
- Loại thiết bị và khả năng hỗ trợ.
- Permission descriptor.
- Permissions Policy.
- Chính sách của hệ điều hành hoặc trình duyệt.

Không gom mọi quyền vào một trạng thái duy nhất kiểu “website đã được cấp toàn bộ quyền”. Quyền luôn gắn với tính năng cụ thể và ngữ cảnh cụ thể.

## 8. Persistent permission trong iframe

Một tài liệu được nhúng có thể cần quyền camera, microphone, geolocation hoặc một tính năng khác. Khi đó, permission còn chịu tác động của Permissions Policy.

Trang cha có thể giới hạn hoặc cho phép delegate feature cho iframe bằng HTTP header:

~~~http
Permissions-Policy: camera=(self "https://meeting.example.test"), microphone=(self "https://meeting.example.test"), geolocation=(self)
~~~

Và thuộc tính `allow` trên iframe:

~~~html
<iframe
  src="https://meeting.example.test/room"
  title="Phòng họp"
  allow="camera; microphone">
</iframe>
~~~

Hai cơ chế có vai trò khác nhau:

- Permissions Policy của trang cha đặt giới hạn cho các tài liệu trong cây frame.
- Thuộc tính `allow` có thể delegate một feature cho iframe trong phạm vi mà policy cha cho phép.
- Permission của người dùng vẫn được trình duyệt kiểm tra riêng.
- API vẫn cần đáp ứng các điều kiện secure context và điều kiện riêng.

`allow` không tự động cấp quyền camera. Nó chỉ cho phép tài liệu con được yêu cầu feature nếu các điều kiện khác được đáp ứng.

### 8.1 Không phải iframe nào cũng có thể xin mọi quyền

Một iframe cross-origin có thể cần được delegate feature rõ ràng. Trình duyệt cũng có thể yêu cầu tương tác của người dùng trong ngữ cảnh top-level hoặc giới hạn việc hiển thị prompt trong frame.

Nếu ứng dụng nhúng không hoạt động:

1. Kiểm tra Permissions Policy response header của trang cha.
2. Kiểm tra thuộc tính `allow` của iframe.
3. Kiểm tra origin của trang cha và trang con.
4. Kiểm tra secure context.
5. Kiểm tra permission state và lỗi thực tế từ API.
6. Kiểm tra quyền hệ điều hành và thiết bị.

Không mở rộng policy cho mọi origin chỉ để làm một iframe hoạt động. Chỉ delegate feature cho nguồn được tin cậy và cần quyền đó.

## 9. Browser permission khác OS permission

Một số tính năng cần được cho phép ở cả trình duyệt lẫn hệ điều hành.

Ví dụ camera:

~~~text
Ứng dụng web
    |
    v
Browser permission cho origin
    |
    v
Quy tắc secure context / Permissions Policy
    |
    v
OS permission cho trình duyệt
    |
    v
Camera device và driver
~~~

Nếu một lớp từ chối, API có thể thất bại dù lớp khác cho phép.

Ví dụ:

- Người dùng đã cho phép camera cho website trong Chrome.
- Nhưng hệ điều hành tắt quyền camera của Chrome.
- Website vẫn không nhận được stream.

Ứng dụng nên xử lý lỗi API và đưa hướng dẫn chung để người dùng kiểm tra cài đặt quyền của trình duyệt hoặc hệ điều hành. Không cố đoán chính xác lớp nào đã từ chối chỉ từ một thông báo lỗi nếu API không cung cấp đủ thông tin.

## 10. Thu hồi quyền và xử lý khi state thay đổi

Người dùng có thể thu hồi permission từ giao diện site settings hoặc privacy settings của trình duyệt. Ứng dụng không có API web tổng quát để tự thu hồi quyết định permission của người dùng.

Một số hành động của ứng dụng chỉ dừng việc sử dụng tài nguyên hiện tại:

- Dừng media tracks.
- Gọi `clearWatch()` cho geolocation.
- Đóng kết nối hoặc dừng tác vụ phụ thuộc feature.
- Xóa dữ liệu cache do chính ứng dụng quản lý.

Những hành động này không đồng nghĩa thu hồi permission ở browser permission store.

### 10.1 Giao diện khi quyền bị thu hồi

Nếu permission đổi từ granted sang denied hoặc prompt trong lúc trang đang mở:

- Dừng tính năng phụ thuộc quyền nếu API báo lỗi hoặc không còn hoạt động.
- Cập nhật trạng thái giao diện.
- Không tự động gọi API liên tục để xin lại.
- Giữ các tính năng không cần quyền vẫn dùng được.
- Giải thích cách người dùng tự đổi quyền trong cài đặt nếu họ muốn.

### 10.2 Không giả định permission state luôn cập nhật tức thì

Sự kiện `change` hữu ích nhưng không phải cơ chế duy nhất để bảo đảm tính đúng đắn. Ứng dụng nên kiểm tra lỗi ở mỗi lần gọi API và xử lý race condition giữa lúc query và lúc sử dụng.

## 11. Thiết kế UX cho persistent permission

Một website có thể giữ quyền lâu dài nên phải thể hiện rõ trách nhiệm khi dùng quyền đó.

### 11.1 Giải thích trước khi gọi API

Thông điệp nên nói rõ:

- Tính năng nào cần quyền.
- Dữ liệu nào sẽ được truy cập.
- Vì sao cần dữ liệu.
- Khi nào dữ liệu được sử dụng.
- Người dùng có thể tắt tính năng hoặc thu hồi quyền ở đâu.

Ví dụ:

~~~text
Cho phép vị trí để hiển thị điểm giao hàng gần bạn.
Vị trí chỉ được yêu cầu khi bạn chọn tìm điểm giao hàng.
Bạn có thể tắt quyền này trong cài đặt website của trình duyệt.
~~~

Không dùng nội dung mơ hồ như “Cho phép để tiếp tục” nếu người dùng chưa biết quyền nào sẽ được xin.

### 11.2 Xin quyền theo hành động

Đặt nút gần tính năng cần quyền, ví dụ “Dùng vị trí hiện tại”, “Bắt đầu cuộc gọi” hoặc “Bật thông báo đơn hàng”.

Tránh xin nhiều quyền cùng lúc nếu tính năng chưa cần đến chúng. Một ứng dụng họp trực tuyến có thể xin camera và microphone khi người dùng bấm tham gia phòng, thay vì xin ngay lúc tải trang chủ.

### 11.3 Cung cấp đường thay thế

Nếu người dùng từ chối vị trí, cho phép nhập địa chỉ thủ công. Nếu không cấp thông báo, vẫn hiển thị trạng thái đơn hàng trong ứng dụng. Nếu không cấp camera, có thể cho phép tham gia cuộc họp chỉ bằng âm thanh.

Từ chối quyền không nên làm mất chức năng không liên quan đến permission đó.

### 11.4 Không coi permission là consent cho mọi mục đích

Người dùng cho phép camera để tham gia cuộc gọi không có nghĩa họ đồng ý ghi hình, lưu trữ hoặc phân tích video ngoài mục đích đã giải thích.

Permission trình duyệt là kiểm soát kỹ thuật truy cập feature. Các nghĩa vụ về thông báo, consent, lưu trữ và xử lý dữ liệu vẫn cần được thiết kế riêng theo mục đích và quy định áp dụng.

## 12. Kiểm thử vòng đời persistent permission

Kiểm thử permission cần thực hiện qua nhiều trạng thái và nhiều vòng đời trình duyệt.

| Tình huống | Điều cần xác minh |
|---|---|
| Lần đầu truy cập | State thường là prompt; API có thể yêu cầu quyết định |
| Sau khi Allow | API hoạt động và state có thể là granted |
| Reload trang | Quyền lâu dài có thể được giữ; quyền tạm thời tùy trình duyệt |
| Đóng và mở lại trình duyệt | Xác định quyết định có được lưu qua phiên hay không |
| Chọn Allow once | Kiểm tra thời điểm quyền hết hiệu lực theo trình duyệt |
| Chọn Block | State và lỗi API phản ánh việc từ chối |
| Thu hồi trong site settings | Ứng dụng nhận biết thay đổi hoặc xử lý lỗi lần gọi tiếp theo |
| Xóa cookie/site data | Xác minh riêng việc xóa dữ liệu có ảnh hưởng permission hay không |
| Profile khác | Xác nhận permission được quản lý độc lập |
| Chế độ riêng tư | Kiểm tra quyền có bị giới hạn hoặc reset khi đóng phiên |
| Tắt quyền ở hệ điều hành | API thất bại dù browser permission có thể vẫn hiển thị granted |
| Nhúng trong iframe | Kiểm tra Permissions Policy và delegation |

### 12.1 Kiểm tra trong DevTools

DevTools giúp quan sát API và lỗi runtime, nhưng không phải lúc nào cũng cung cấp giao diện đầy đủ để thay đổi permission store.

Hãy dùng:

- Console để đọc `navigator.permissions.query()`.
- Application hoặc Security panel nếu trình duyệt cung cấp thông tin liên quan.
- Network để kiểm tra header Permissions-Policy.
- Elements để xem thuộc tính `allow` của iframe.
- Browser site settings để xem và thu hồi permission.
- OS privacy settings để kiểm tra quyền của ứng dụng trình duyệt.

Ghi rõ trình duyệt, phiên bản, profile, chế độ duyệt và loại permission khi lập báo cáo kiểm thử.

## 13. Ví dụ: quản lý trạng thái vị trí trong giao diện

Ví dụ sau query permission, theo dõi thay đổi và chỉ lấy vị trí khi người dùng bấm nút.

~~~html
<p id="permission-state">Đang kiểm tra quyền vị trí...</p>
<button id="use-location">Dùng vị trí hiện tại</button>
<p id="location-result"></p>
~~~

~~~js
const stateLabel = document.querySelector("#permission-state");
const resultLabel = document.querySelector("#location-result");
const useLocationButton = document.querySelector("#use-location");

let geolocationPermission = null;

function renderState(state) {
  stateLabel.textContent = "Quyền vị trí: " + state;
}

async function setupPermissionStatus() {
  if (!navigator.permissions) {
    renderState("không thể truy vấn trên trình duyệt này");
    return;
  }

  try {
    geolocationPermission = await navigator.permissions.query({
      name: "geolocation"
    });

    renderState(geolocationPermission.state);

    geolocationPermission.addEventListener("change", () => {
      renderState(geolocationPermission.state);
    });
  } catch (error) {
    renderState("không hỗ trợ descriptor hoặc không truy vấn được");
  }
}

useLocationButton.addEventListener("click", () => {
  if (!navigator.geolocation) {
    resultLabel.textContent = "Trình duyệt không hỗ trợ vị trí.";
    return;
  }

  navigator.geolocation.getCurrentPosition(
    position => {
      const { latitude, longitude } = position.coords;
      resultLabel.textContent =
        "Vị trí: " + latitude + ", " + longitude;
    },
    error => {
      resultLabel.textContent =
        "Không lấy được vị trí: " + error.message;
    }
  );
});

setupPermissionStatus();
~~~

Trong ví dụ:

- Query chỉ hiển thị trạng thái, không xin quyền.
- Nút mới gọi Geolocation API.
- Ứng dụng lắng nghe `change` để cập nhật giao diện.
- API vẫn có callback lỗi vì permission có thể bị từ chối hoặc điều kiện runtime không đáp ứng.

Trong sản phẩm thực tế, không nên ghi tọa độ chính xác vào log nếu không cần. Hãy giới hạn thời gian lưu và chỉ xử lý dữ liệu vị trí cho mục đích đã giải thích.

## 14. Những nhầm lẫn thường gặp

### 14.1 Nghĩ granted có nghĩa là vĩnh viễn

Granted chỉ phản ánh trạng thái hiện tại. Người dùng, trình duyệt, hệ điều hành hoặc quản trị viên có thể thay đổi quyền.

### 14.2 Nghĩ query sẽ hiện prompt

`navigator.permissions.query()` chỉ truy vấn state. API riêng mới thực hiện quy trình xin hoặc sử dụng permission.

### 14.3 Nghĩ xóa cookie sẽ thu hồi mọi quyền

Permission store và dữ liệu website có thể được quản lý riêng. Kiểm tra site settings của trình duyệt.

### 14.4 Nghĩ dừng camera sẽ thu hồi permission

Dừng track kết thúc stream hiện tại, nhưng quyết định cấp quyền có thể vẫn được lưu.

### 14.5 Nghĩ browser permission granted là đủ

OS permission, Permissions Policy, secure context, thiết bị và điều kiện API vẫn có thể chặn thao tác.

### 14.6 Nghĩ iframe được cấp quyền chỉ bằng thuộc tính allow

`allow` delegate feature trong phạm vi policy cha. Người dùng vẫn phải cấp permission khi cần.

### 14.7 Nghĩ mọi trình duyệt lưu quyền giống nhau

Thời hạn, quyền một lần, auto-reset, giao diện và cách lưu khác nhau. Cần kiểm thử trên ma trận trình duyệt mục tiêu.

### 14.8 Nghĩ permission là consent cho mọi mục đích xử lý dữ liệu

Permission cho phép API truy cập feature. Mục đích thu thập, ghi âm, lưu trữ và chia sẻ dữ liệu cần được giải thích và quản lý riêng.

## 15. Bài thực hành

Thực hiện trên website HTTPS do bạn kiểm soát. Dùng dữ liệu thử nghiệm và thiết bị của chính bạn.

### Bài 1: Quan sát ba permission state

Tạo trang lab có nút kiểm tra geolocation permission. Lần lượt giữ trạng thái prompt, cấp quyền và từ chối quyền trong site settings. Ghi nhận state trả về và lỗi API tương ứng.

### Bài 2: Kiểm tra quyền sau reload

Cấp quyền vị trí theo lựa chọn của trình duyệt. Reload trang, đóng tab, khởi động lại trình duyệt và truy cập lại. So sánh quyền được lưu và quyền tạm thời.

### Bài 3: Thu hồi khi trang đang mở

Mở trang lab, cấp quyền và để trang hoạt động. Từ site settings, thu hồi quyền. Quan sát sự kiện `PermissionStatus.change` nếu trình duyệt phát sự kiện và kiểm tra lần gọi API tiếp theo.

### Bài 4: So sánh profile

Dùng hai profile trình duyệt khác nhau để truy cập cùng origin. Cấp quyền ở profile thứ nhất và giữ prompt ở profile thứ hai. Ghi lại sự khác biệt.

### Bài 5: Kiểm tra browser và OS permission

Cấp quyền camera cho website, sau đó tắt quyền camera của trình duyệt trong cài đặt hệ điều hành. Gọi `getUserMedia()` và ghi nhận lỗi. Bật lại quyền hệ điều hành và kiểm tra lần nữa.

### Bài 6: Kiểm tra iframe delegation

Tạo trang cha và iframe khác origin. Thử dùng camera với Permissions Policy bị chặn, sau đó delegate feature bằng header và thuộc tính `allow`. Xác nhận người dùng vẫn cần cấp browser permission nếu trình duyệt yêu cầu.

## 16. Checklist review Persistent permission

- [ ] Đã xác định chính xác API và permission name cần dùng.
- [ ] Chỉ xin quyền khi người dùng hiểu tính năng và chủ động bắt đầu.
- [ ] Giao diện giải thích mục đích, loại dữ liệu và cách thu hồi.
- [ ] Không coi state granted là quyền vĩnh viễn.
- [ ] Query permission được tách khỏi thao tác xin quyền.
- [ ] Có xử lý prompt, granted, denied và trường hợp API không hỗ trợ query.
- [ ] Có xử lý lỗi API dù state trước đó là granted.
- [ ] Có theo dõi PermissionStatus change khi phù hợp.
- [ ] Có dừng stream, watch hoặc tác vụ khi người dùng kết thúc tính năng.
- [ ] Đã kiểm tra secure context và Permissions Policy.
- [ ] Iframe chỉ được delegate feature cho origin cần thiết.
- [ ] Đã kiểm tra quyền hệ điều hành đối với thiết bị.
- [ ] Đã kiểm thử reload, restart, profile riêng tư và auto-reset.
- [ ] Đã phân biệt permission với cookie, site data và persistent storage.
- [ ] Có phương án thay thế khi người dùng từ chối.
- [ ] Không dùng permission như consent chung cho mọi mục đích xử lý dữ liệu.

## 17. Câu hỏi tự kiểm tra

**1. Persistent permission là gì?**

Là quyết định cấp quyền mà trình duyệt có thể lưu để origin tiếp tục sử dụng tính năng trong các lần truy cập sau mà không cần hỏi lại mỗi lần.

**2. Granted có nghĩa quyền tồn tại vĩnh viễn không?**

Không. Người dùng, trình duyệt, hệ điều hành hoặc quản trị viên có thể thu hồi, reset hoặc giới hạn quyền.

**3. Ba trạng thái chuẩn của Permissions API là gì?**

`granted`, `denied` và `prompt`.

**4. navigator.permissions.query() có hiện hộp thoại xin quyền không?**

Không. Nó chỉ truy vấn trạng thái permission hiện tại.

**5. Permissions API có cho biết thời hạn của permission không?**

Không. API không cung cấp thời điểm cấp hoặc thời hạn chuẩn của quyền.

**6. Dừng MediaStream có thu hồi permission camera không?**

Không. Dừng track kết thúc stream hiện tại; quyền đã lưu trong trình duyệt có thể vẫn còn.

**7. Vì sao API có thể thất bại dù state là granted?**

Vì hệ điều hành, Permissions Policy, secure context, thiết bị hoặc điều kiện riêng của API vẫn có thể ngăn thao tác.

**8. Thuộc tính allow của iframe có tự cấp quyền cho người dùng không?**

Không. Nó chỉ delegate feature trong giới hạn Permissions Policy; browser permission vẫn được kiểm tra riêng.

**9. Xóa cookie có chắc chắn xóa permission không?**

Không. Dữ liệu website và permission store có thể được quản lý riêng trong cài đặt trình duyệt.

**10. Ứng dụng nên làm gì khi người dùng từ chối quyền?**

Tôn trọng quyết định, không lặp prompt, cung cấp hướng dẫn thay đổi cài đặt nếu người dùng muốn và giữ các tính năng không phụ thuộc quyền hoạt động bình thường.

## Ghi nhớ

Persistent permission là quyết định do trình duyệt quản lý và có thể được lưu qua nhiều lần truy cập. Nó luôn có thể thay đổi theo người dùng, profile, trình duyệt, hệ điều hành và chính sách nhúng. Hãy query trạng thái thay vì đoán thời hạn, xin quyền khi có hành động rõ ràng, xử lý lỗi ở mỗi lần gọi API và cung cấp cách thu hồi hoặc dùng tính năng thay thế.

## Tài liệu tham khảo

- [MDN: Permissions API](https://developer.mozilla.org/en-US/docs/Web/API/Permissions_API)
- [MDN: Permissions](https://developer.mozilla.org/en-US/docs/Web/API/Permissions)
- [MDN: PermissionStatus](https://developer.mozilla.org/en-US/docs/Web/API/PermissionStatus)
- [MDN: Permissions Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy)
- [W3C: Permissions](https://www.w3.org/TR/permissions/)
