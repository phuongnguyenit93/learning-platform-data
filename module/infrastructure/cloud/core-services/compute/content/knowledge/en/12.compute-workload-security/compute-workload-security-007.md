# Measured boot, attestation, and execution environment verification

A virtual machine may be launched from an approved image yet still boot with different firmware, bootloader, kernel, or configuration than expected. In multi-account and multi-region environments, operations teams need evidence showing which platform the machine runs on, what components were loaded during boot, and whether the workload satisfies security policy before receiving sensitive data.

**Measured boot** records cryptographic measurements of components during the boot sequence. **Attestation** uses that evidence so another party can evaluate the state of the device or workload against a defined policy. Combined with Secure Boot, TPM, key management systems, and image release pipelines, organizations can detect deviations in the boot chain and grant access only to compliant environments.

This lesson explains the foundations of measured boot, TPM PCRs, event logs, local and remote attestation, how a verifier reaches decisions, how to gate secrets or workloads on those results, and limitations to understand before going to production.

## 1. Why verify the execution environment?

A VM can report a running state even when the OS booted with an unintended configuration. For example:

- Firmware or the bootloader was altered.
- The machine booted an image version other than the approved one.
- Secure Boot was disabled or boot key configuration changed.
- The kernel, initramfs, or kernel command-line parameters deviate from baseline.
- An outdated, vulnerable boot component is still in use.
- The VM was launched in a non-compliant project/account or host.
- A workload runs in a confidential VM without verifying evidence of the protected environment.
- Secrets are issued to an instance based solely on deployer-controlled tags or metadata.

Inventory, image IDs, and cloud control-plane state are important signals, yet insufficient to prove actual boot state. Measured boot adds evidence generated on the machine and anchored in security hardware or platform attestation mechanisms.

### Questions to answer

An environment verification workflow typically needs to establish:

1. Does the platform have an appropriate root of trust?
2. Which components were measured by the boot chain?
3. Do measured values match an approved version?
4. Is the evidence fresh and bound to the exact machine under inspection?
5. Were any components bypassed or unmeasured?
6. Does the environment satisfy policy before receiving secrets or traffic?
7. When the OS or image is updated, how is the baseline updated and approved?

Attestation does not replace overall system security. It provides a verifiable signal to combine with machine identity, network policies, vulnerability management, runtime monitoring, and access control.

## 2. Root of trust and the boot chain

### What is a root of trust?

A root of trust is the minimal component or mechanism a system relies upon to verify subsequent steps. In a boot chain, firmware or security hardware can provide the starting anchor for signature verification and measurement.

A typical boot sequence looks like:

1. CPU and firmware begin execution.
2. Firmware initializes hardware and verifies or measures subsequent components.
3. Boot manager/bootloader is verified or measured.
4. Bootloader loads the kernel and initramfs.
5. Kernel initializes drivers, modules, and the root filesystem.
6. Init system starts OS services.
7. Security agents, workloads, and applications start.

The exact sequence depends on BIOS/UEFI architecture, OS, hypervisor, and cloud platform. Not every component is measured identically across all machines.

### Chain of trust

A chain of trust is a model where each stage verifies or measures the next component before transferring control. If a component fails verification, the system can refuse to boot, fall back to recovery, or record a non-compliant state.

Distinguish two actions:

- **Verify:** check signatures or integrity before allowing execution.
- **Measure:** compute a cryptographic digest of a component and record it in a protected measurement area.

A validly signed component can still contain vulnerabilities. A signature proves publisher identity and integrity under trusted keys, not that software is bug-free. Measuring lets a verifier see the exact version or state loaded and compare it against policy.

### Firmware and boot configuration

Firmware can govern boot mode, Secure Boot, trusted key lists, boot devices, and boot order. Changes to these settings can alter measurement results.

In VM environments, some firmware state is virtualized. The hypervisor and cloud provider determine how firmware, vTPM, and measurements are exposed to the guest. Do not assume a VM carries identical hardware guarantees to a physical server simply because the OS sees a TPM.

## 3. How Secure Boot differs from measured boot

Secure Boot and measured boot are related but answer different questions.

| Mechanism | Goal | Action | Outcome |
|---|---|---|---|
| Secure Boot | Prevent untrusted boot components from executing | Verify signatures against keys and trust policies | Allow or block the boot component |
| Measured boot | Record the state of loaded components | Compute hashes and extend values into PCRs | Evidence of the measured boot chain |
| Attestation | Evaluate evidence against policy | Collect quotes, event logs, and claims, then verify | Conclude pass, fail, or indeterminate |

### Secure Boot

UEFI Secure Boot uses key and signature databases to verify bootloaders or boot components against policy. If a signature is untrusted or revoked, firmware can block that component from executing.

Secure Boot reduces the risk of bootkits and unapproved boot components. However, a validly signed bootloader with a known vulnerability may still be accepted if keys and revocation lists have not yet accounted for it.

### Measured boot

Measured boot records measurements of firmware, boot managers, and configured measured components. It does not necessarily stop a component from running. Instead, measurement results can be sent to a verifier for comparison against a baseline.

If an unfamiliar bootloader still executes and gets measured, the PCRs will differ from expected values. A verifier can refuse to release secrets or flag the machine for investigation.

### Combining both mechanisms

A common pattern enables Secure Boot to block unsigned components per policy while also enabling measured boot to record boot-chain state. Remote attestation then verifies those measurements and additional claims before granting access.

Do not treat a Secure Boot enabled flag as sole proof. Verify keys, revocation status, firmware mode, measurements, and active policies.

## 4. TPM and Platform Configuration Registers

### What is a TPM?

A Trusted Platform Module (TPM) is a security component providing functions such as key generation and protection, performing measurements, storing security state, and producing cryptographic evidence. TPM 2.0 is the prevalent version in modern platforms.

A TPM can be a physical chip on a server or a virtual TPM (vTPM) exposed to a VM by the hypervisor. Implementation details, key protection strength, and vTPM trust boundaries depend on the platform.

### What do PCRs store?

A Platform Configuration Register (PCR) stores measurement state. A PCR does not simply hold the latest hash of a single file. When a new measurement arrives, the PCR value is extended according to:

\[
PCR_{new} = H(PCR_{old} \parallel measurement)
\]

Where H is the chosen hash function and \(\parallel\) denotes concatenation. Because the new value depends on both the old value and the new measurement, measurement order affects the final result.

PCRs are typically grouped by purpose and platform profile. Some systems assign dedicated PCRs for firmware, boot managers, Secure Boot policies, or other settings. However, PCR assignments vary across firmware and platforms. Verifiers must understand the specific profile rather than hardcoding universal assumptions across all machines.

### Why are PCRs useful?

PCRs reside within the TPM's protection boundary. Regular software cannot arbitrarily write a chosen value into a PCR the way it writes a disk file. Extend operations follow TPM rules, making measurement results hard to forge from inside the guest OS.

PCRs can be used to:

- Compare boot state against a baseline.
- Bind key usage to a specific PCR state.
- Generate a TPM-signed quote proving measured state at request time.
- Detect changes to measured firmware, bootloaders, or boot policies.

PCRs do not contain human-readable descriptions of every component. To determine which event corresponds to each measurement, verifiers generally need an event log.

## 5. Event logs and interpreting measurements

### What is an event log?

During boot, measuring components can record events including module name, event type, component digest, and target PCR extended. Events are stored in an event log so a verifier can interpret them.

An event log may contain:

- Loaded firmware components.
- Boot manager or bootloader entries.
- Kernel, initramfs, or driver entries.
- Secure Boot configuration and associated keys.
- Components measured by extensions such as Linux IMA, if enabled.

Log contents and formats depend on the platform. Not every event is a file hash; some events describe configuration or boot-related data.

### Replaying the event log

A verifier can read the event log, start from the standard initial PCR value, and sequentially apply the extend operation for each digest. The reconstructed value must match the PCR reported in the TPM quote.

This process detects tampered event logs or logs inconsistent with TPM state. If the log cannot replay to the quoted PCR, the evidence is invalid or incomplete.

### Measurements and reference values

Reference values are expected values published by a trusted organization or vendor for a specific configuration. They may be organized by:

- Machine model or VM type.
- Firmware version.
- Boot mode and Secure Boot policy.
- Bootloader, kernel, and initramfs versions.
- Image release and OS configuration.
- Versions of measured agents or modules.

An overly broad baseline may accept unintended configurations. An overly narrow baseline may reject legitimate updates. Manage reference values with versioning, provenance, approvers, and validity windows.

### Event logs are not standalone evidence

Event logs are typically collected from the OS or firmware and could be altered after creation. Always cross-check logs against a TPM-signed PCR quote. Never trust an event log solely because it came from the machine under verification.

## 6. Quotes and local attestation

### TPM quote

A TPM quote is an evidence structure in which the TPM signs a selected set of PCRs together with associated metadata. Quotes are typically signed with an Attestation Key (AK) or equivalent attestation key.

A quote may include:

- Digests of the requested PCRs.
- Hash algorithm details.
- A nonce or qualifying data supplied by the verifier.
- Timestamps or counters per TPM mechanisms.
- Signature from the attestation key.

The verifier checks the signature, validates the attestation key, and compares the nonce to confirm the quote was freshly generated for the current request.

### Nonces against replay

Without a nonce or equivalent freshness mechanism, an attacker could replay an older, previously valid quote. The verifier generates a random nonce per attestation session, sends it to the device, and requires the quote to include that nonce.

Upon receiving the quote, the verifier confirms the nonce matches the freshly issued value and has not been used before. Thus, old evidence cannot be replayed to pass a new check.

Nonces must be sufficiently random, short-lived, and bound to a specific verification session.

### Local attestation

Local attestation evaluates state directly on the device or within the same trust domain. For example, a TPM can allow unsealing a key only when PCRs match a configured policy.

Some applications use TPM policies to bind signing or decryption operations to boot state. If measured state changes, the TPM refuses to release the key.

Local attestation is useful for protecting keys on the same host, but does not replace remote attestation when an external service must verify a VM before releasing data.

## 7. Remote attestation and the verifier's role

Remote attestation lets an independent party assess a machine's state remotely. For instance, a secret manager or workload identity issuer may want to verify a VM before delivering credentials.

### Key components

- **Attester:** the machine or workload generating evidence.
- **Evidence:** quotes, event logs, certificates, claims, and related data.
- **Verifier:** the system validating signatures, freshness, reference values, and policies.
- **Relying party:** the service acting on the result to grant or deny access.
- **Reference values:** approved baselines used for comparison.
- **Attestation policy:** rules determining which states are acceptable.

The verifier may be a standalone service, part of a secret manager, an identity system, or a cloud provider's attestation service.

### Remote attestation flow

~~~mermaid
sequenceDiagram
    participant V as Verifier
    participant A as Attester VM
    participant T as TPM or platform
    participant R as Relying Party

    V->>A: Send challenge nonce
    A->>T: Request PCR quote with nonce
    T-->>A: Signed quote
    A-->>V: Quote, event log, and claims
    V->>V: Verify certificates, signature, and nonce
    V->>V: Replay log and compare reference values
    V->>R: Time-limited attestation result
    R->>A: Grant or deny access
~~~

### Steps a verifier must execute

1. Identify the attester and accepted evidence types.
2. Validate the certificate chain or attestation key identity.
3. Verify the quote carries a valid signature.
4. Check the nonce and freshness.
5. Confirm quoted PCRs match policy requirements.
6. Replay the event log and compare digests against PCRs.
7. Compare reference values against approved baselines.
8. Evaluate revocation status, firmware versions, and policies.
9. Validate additional claims such as instance identity, region, or workload measurements.
10. Return a time-bounded result with scope and pass/fail rationale.

Results should distinguish at least three outcomes:

- **Pass:** evidence is valid and satisfies the full policy.
- **Fail:** evidence is valid but the state violates policy.
- **Indeterminate:** evidence is missing, signatures fail verification, the event log is malformed, or the verifier lacks sufficient data.

Never turn a verifier error or timeout into a pass. For sensitive data, policies should generally fail closed or restrict privileges when the outcome is indeterminate.

## 8. Image, boot state, and runtime verification are three distinct layers

Measured boot typically focuses on the startup chain. To evaluate an environment thoroughly, distinguish three layers:

| Layer | Typical evidence | Question answered | Limitations |
|---|---|---|---|
| Image/provenance | Image ID, artifact signatures, build manifests, SBOMs | Did the image come from a trusted pipeline and receive approval? | Does not prove that exact image actually booted or remained unaltered afterward |
| Boot state | TPM PCRs, quotes, and event logs | Do measured boot components match baseline? | Does not automatically prove all post-boot processes are safe |
| Runtime/workload | IMA measurements, EDR, workload identity, process policies, TEE reports | Does the running workload or environment satisfy additional policies? | Coverage depends on measurement mechanism, scope, and trust boundaries |

A validly signed image can still boot with different firmware or kernels if configuration permits. A passing boot state likewise does not prove an application lacks vulnerabilities or has not been exploited after boot.

Therefore, workflows should combine image provenance, measured boot, runtime monitoring, and workload policies.

### Runtime measurement with Linux IMA

Linux Integrity Measurement Architecture (IMA) can measure or appraise accessed/executed files per policy. Digests can be extended into PCRs and recorded in a measurement list.

IMA helps track post-boot file changes, though coverage depends on policy and kernel configuration. If a policy only measures selected paths, files outside that scope remain unverified. Policies, event logs, and reference values must be managed separately.

Do not claim measured boot proves full runtime state if you only collect traditional boot PCRs.

## 9. Attestation for confidential VMs and trusted execution environments

### What is confidential computing?

Confidential computing uses hardware mechanisms to protect data in use, typically through memory encryption and access controls between the guest and host or hypervisor. The goal is to limit the host or privileged software from reading workload memory contents.

Technologies you may encounter:

- AMD SEV-SNP for confidential VMs on supported platforms.
- Intel TDX for confidential VMs on supported platforms.
- Arm Confidential Compute Architecture (CCA) in compatible implementations.
- Trusted Execution Environments (TEEs) for isolated execution regions within a system.

These mechanisms differ in threat models, evidence formats, and limitations. Do not treat every VM with disk encryption or a vTPM as a confidential VM.

### TEE attestation reports

Confidential VMs can produce attestation reports containing measurements of firmware, boot chains, or guest protection state alongside platform claims. Reports may be signed by hardware or a provider security service.

Verifiers inspect:

- Signatures and root certificate chains.
- Guest or firmware measurements.
- TCB (Trusted Computing Base) versions.
- Security update and revocation status.
- Policies on debugging, migration, or protection attributes.
- Nonces or challenge data bound to the verification session.
- Workload claims where supported.

A valid report only indicates that evidence aligns with the chosen trust model and policy. It does not guarantee the application has no logic bugs, secrets are not logged, or data cannot be exfiltrated.

### Distinguishing vTPM and confidential VMs

A vTPM exposes a virtual TPM interface to the guest. It stores PCRs and generates quotes under a hypervisor-managed model. Protection strength depends on how the provider stores keys, isolates the vTPM, and verifies the host.

A confidential VM uses hardware mechanisms to protect guest memory and can produce dedicated attestation evidence for its confidential computing state. A confidential VM may include a vTPM, yet the two concepts are not synonymous.

## 10. Using attestation to gate secrets and access

A practical application is issuing secrets or tokens only when a VM proves its boot state satisfies policy.

### Conditional secret release flow

1. The VM boots and generates a quote.
2. The VM sends evidence to the attestation verifier.
3. The verifier validates the quote, event log, and reference values.
4. The verifier returns a signed result or short-lived token.
5. The secret manager validates the result and workload identity.
6. The secret manager releases only secrets matching the role and environment.
7. Tokens expire quickly; workloads re-verify periodically or upon major changes.

Attestation results must bind to a specific VM or workload identity rather than returning a generic boolean. If you only have "attestation passed" without identifying the machine, timestamp, and policy version, relying parties struggle to scope access.

### Scoping audience and lifetime

Attestation tokens should include:

- Subject: the verified machine or workload.
- Audience: the sole service permitted to accept the token.
- Short issued-at and expiry windows.
- Policy ID/version.
- Evaluated measurements or state.
- Nonce/session ID or binding to the verification session.
- Verifier signature.

Relying parties must check audience, expiration, signature, and subject identity. Never accept a token issued for one service at another service unless explicitly permitted by policy.

### Avoid issuing long-lived secrets

Even when attestation passes, prefer short-lived credentials and least privilege. If a VM is compromised after boot, long-lived secrets remain usable afterward. Maintain rotation, revocation, auditing, and re-evaluation mechanisms.

### Handling attestation failures

If the verifier returns fail or indeterminate:

- Deny sensitive secrets.
- Keep the VM out of load balancers if policy requires.
- Record the reason and evidence ID in audit logs.
- Trigger controlled recovery or reimaging workflows.
- Never automatically downgrade policy just to let machines keep running.

For systems requiring high availability, a degraded mode permitting only non-sensitive tasks can be used, provided it is explicitly defined in policy.

## 11. Managing reference values and system updates

### Baselines must have provenance

Reference values should be derived from tested images and firmware, never captured arbitrarily from a running machine merely because it seems stable.

A standard workflow:

1. Build the image from approved sources.
2. Update firmware, bootloader, and OS.
3. Boot on the target hardware configuration.
4. Capture the event log and PCRs via attestation.
5. Verify the boot chain and expected software.
6. Approve the baseline alongside image/firmware versions.
7. Store the manifest, signature, and validity window.
8. Distribute the baseline to verifiers.

Tie baselines to machine types, firmware profiles, architectures, and boot configurations. Never compare PCRs across two different platforms merely because they run the same Linux version.

### Firmware and kernel updates can change PCRs

Updates to firmware, bootloaders, kernels, initramfs, or Secure Boot databases can alter PCRs. This is not automatically a sign of attack. The verifier needs to know whether the new version is valid.

Multiple baselines can be managed concurrently during rollouts:

- Current approved baseline.
- New baseline undergoing canary validation.
- Prior baseline retained for a brief rollback window.
- Revoked baselines when critical vulnerabilities arise.

Never retain old baselines indefinitely. A policy permitting every historical version can inadvertently accept a revoked bootloader or firmware.

### Change approval

Reference value updates require review, signing, and auditing. Record the rationale, image/firmware version, scope, approver, and expiration date.

Never auto-enroll every newly observed measurement into an allowlist. If a machine is compromised, auto-learning measurements from it turns a malicious state into a trusted baseline.

## 12. Deploying attestation in multi-VM environments

### Policy grouping

An organization typically manages multiple workload tiers:

- Development: test data; policies can be more flexible while still verifying image provenance.
- Staging: mirrors production; uses near-equivalent baselines.
- Production: strict policies accepting only approved images and firmware.
- Sensitive workloads: require confidential VMs, TEEs, or enhanced attestation.
- Disaster recovery: baselines and key policies must function in failover regions.

Each group needs explicit policies rather than one overly broad organization-wide allowlist.

### Integration with orchestration

In self-managed VM fleets, provisioning workflows can wait for attestation before registering machines in load balancers or issuing credentials.

In Kubernetes or container environments, attestation may apply to nodes, confidential workloads, or security agents depending on platform. Distinguish node attestation from image/container verification. An attested node does not automatically prove every container on it is trustworthy.

### Periodic re-verification

Boot attestation typically runs at startup. If required by policy, re-verify periodically or before sensitive operations. However, boot PCR quotes do not automatically update to reflect every runtime change. For runtime integrity, use dedicated measurement mechanisms such as IMA, EDR, or TEE attestation supporting workload state.

### Scaling the verifier

A verifier must be able to:

- Handle high quote volume without becoming a bottleneck.
- Cache signed, versioned reference values.
- Write audit logs without recording unnecessary sensitive data.
- Track expiring certificates, revocations, and TCB status.
- Maintain high availability and recovery plans.
- Reject expired requests or reused nonces.
- Perform controlled policy updates.

If the verifier is unavailable, relying parties must follow predefined behavior. Never automatically grant sensitive access when verification cannot run.

## 13. Observability, auditing, and troubleshooting

### Metrics to monitor

- Attestation pass, fail, and indeterminate rates.
- Latency from challenge to result.
- Count of invalid quotes or replayed nonces.
- Count of machines with PCR mismatches against baseline.
- Count of reference values nearing expiration.
- Attestation certificates nearing expiration or revoked.
- Rate of VMs failing to complete boot measurement.
- Secret access denials caused by attestation policies.
- Health of verifiers and reference value services.

### Audit records

Each verification should record:

- Attester/workload ID.
- Timestamp and challenge/session ID.
- Policy ID and policy version.
- Reference value set used.
- Outcome: pass/fail/indeterminate.
- Rejection reason or failed claims.
- Evidence digest or ID for controlled retrieval.
- Relying-party decision, such as secret issued or denied.

Never log private keys, secrets, full tokens, or sensitive workload data in audit logs.

### Common issues

| Symptom | Possible cause | What to check |
|---|---|---|
| TPM not detected | vTPM disabled, missing driver or firmware | Check VM config, TPM device, and guest drivers |
| Quote fails verification | Wrong AK certificate, signature, or algorithm | Check trust chain, key enrollment, and PCR hash algorithm |
| Nonce mismatch | Stale quote, mixed-up sessions, or challenge implementation bug | Check nonce, session binding, and timeouts |
| Event log replay does not match PCR | Missing log entries, wrong order, unsupported format, or tampering | Re-collect log, check profile and hash algorithm |
| PCR differs from baseline after update | Firmware, bootloader, kernel, or Secure Boot policy changed | Compare event log and release manifest; verify update |
| Secure Boot enabled yet attestation fails | Keys, PCRs, TCB, or policies differ from baseline | Inspect all claims, not just Secure Boot status |
| Attestation passes yet app compromised | Only boot measured, no runtime integrity | Add IMA/EDR, workload controls, and monitoring |
| Secret manager rejects token | Wrong audience, subject, policy version, or expiry | Check token claims and identity mapping |
| Confidential VM report invalid | Unsupported certificates, TCB status, or report format | Update verifier and reference data from trusted sources |

### Investigation workflow

1. Identify the machine and image/firmware version under inspection.
2. Verify availability of the TPM/vTPM or attestation device.
3. Capture a fresh quote with a new nonce.
4. Validate certificates and signatures.
5. Inspect the event log and replay PCRs.
6. Compare each differing event against release manifests.
7. Determine whether the change was approved.
8. Check TCB status and revocation state if using confidential computing.
9. Decide whether to keep the machine quarantined, update baselines, or reimage.
10. Save audit records and update procedures if a gap is found.

Never add unverified measurements to an allowlist just to make a pipeline green again.

## 14. Limitations and common misconceptions

1. **Secure Boot equals measured boot.** Secure Boot verifies signatures; measured boot records measurements. You can enable one without the other.
2. **A TPM means the machine is completely secure.** A TPM provides primitives and a protection boundary; overall quality depends on firmware, provisioning, policies, and the verifier.
3. **PCRs are a list of file hashes.** PCRs are sequentially extended states; the event log provides event context.
4. **An event log proves its own integrity.** Logs must be verified against a signed quote.
5. **A valid quote means boot state is good.** A valid quote proves only that the TPM signed the selected PCRs; the verifier must still check the nonce, reference values, and policy.
6. **Measured boot proves runtime is untampered.** Boot measurements do not automatically track all post-boot changes.
7. **A running VM means the workload is ready.** Attestation and application readiness are separate conditions.
8. **A vTPM is identical to a physical TPM.** Protection guarantees depend on the hypervisor, provider, and trust model.
9. **Confidential VMs are automatically trustworthy.** You still must verify reports, TCB, measurements, and policies.
10. **A PCR mismatch is always an attack.** Legitimate updates also alter PCRs; manage baselines by version.
11. **Passing attestation justifies releasing all secrets.** Secrets still require scoping, audience, identity, short lifetimes, and least privilege.
12. **When the verifier fails, allow access to preserve availability.** For sensitive resources, failing open defeats the entire attestation control.

### Attestation is not a software quality certification

An environment with a valid boot chain can still run an application with vulnerabilities, misconfigurations, or unsafe logic. Attestation is a signal about measured state and environment provenance, not proof that every line of code is bug-free.

## 15. Example: releasing secrets only to VMs with approved boot state

An internal service permits only production VMs to retrieve database connection secrets. The platform team standardized the image, enabled Secure Boot and measured boot, and registered reference values by VM type.

Processing flow:

1. A production VM boots from an approved image version.
2. An agent on the VM requests a challenge from the verifier.
3. The verifier returns a unique nonce.
4. The agent asks the TPM to quote the PCR set specified by policy.
5. The VM sends the quote, event log, and workload identity to the verifier.
6. The verifier validates signatures, nonce, event log replay, and reference values.
7. The verifier confirms image/firmware versions match production policy.
8. On pass, the verifier issues a short-lived token scoped to the secret manager audience.
9. The secret manager verifies the token and workload identity.
10. The secret manager releases the exact secret with short lifetime and minimal permissions.
11. On fail or indeterminate, the VM receives no secrets and is kept away from sensitive traffic.

### Illustrative policy

~~~yaml
attestation_policy:
  id: production-vm-policy
  version: "3"
  subject:
    environment: production
    workload: payments-api
  requirements:
    secure_boot: enabled
    measured_boot: required
    tpm_quote: required
    fresh_nonce: required
    event_log_replay: required
    reference_values:
      - image-release-2026.11
      - firmware-profile-prod-v2
  decision:
    pass: allow_scoped_secret
    fail: deny_and_quarantine
    indeterminate: deny_sensitive_access
  token:
    audience: secret-manager
    max_ttl_seconds: 300
~~~

This is an illustrative policy, not a provider's standard schema. In production, bind policies to attestation key identity, PCR profile, algorithms, TCB status, region/account, and reference value provenance.

### Checking on Linux

On systems with TPM 2.0 and `tpm2-tools`, basic inspection commands include:

~~~sh
# Inspect TPM device and PCR state
ls -l /dev/tpm*
tpm2_getcap properties-fixed
tpm2_pcrread sha256:0,2,4,7
~~~

The PCR indices shown are merely a commonly inspected set on certain PC/UEFI profiles. Do not apply the same list blindly across all cloud VMs. Determine PCR selection from your platform's firmware profile and policy.

You can check Secure Boot status using your distribution's appropriate tool, for example:

~~~sh
mokutil --sb-state
~~~

This command checks Secure Boot status on supported environments; it does not replace TPM quotes or remote attestation.

TPM event logs may be exposed through firmware interfaces or OS utilities. Paths and formats depend on kernel, firmware, and image. Use compatible tools to collect the log, then replay it alongside the quote in the verifier.

## 16. Roadmap for deploying measured boot and attestation

A controlled rollout roadmap:

1. **Define the threat model:** what changes to firmware, bootloader, kernel, host, or runtime are you defending against?
2. **Choose the trust anchor:** physical TPM, vTPM, platform attestation service, or TEE.
3. **Select the measurement profile:** PCRs, event logs, hash algorithms, and components to check.
4. **Standardize images:** firmware mode, Secure Boot, bootloader, kernel, and boot configuration.
5. **Capture baselines:** measure from clean, tested environments—never auto-learn from arbitrary production hosts.
6. **Build the verifier:** validate trust chains, quotes, nonces, event logs, and reference values.
7. **Define policies:** pass/fail/indeterminate handling, subject scope, audience, and lifetimes.
8. **Integrate relying parties:** secret managers, workload identity, load balancers, or control planes.
9. **Canary:** enable attestation on a small group and watch false rejections and latency.
10. **Expand:** roll out by environment, region, and VM type.
11. **Operate baselines:** handle updates, revocations, and rollbacks with formal approval.
12. **Run incident drills:** anomalous quotes, unavailable TPM, verifier outages, and firmware updates.

### Acceptance criteria

- VMs generate quotes from registered TPM/attestation services.
- Verifiers detect invalid signatures or invalid nonces.
- Event log replay matches PCRs in valid cases.
- Unapproved boot component changes cause policy failure.
- Valid updates are added to baselines via approval workflows.
- Secret managers reject expired tokens, wrong audiences, or wrong subjects.
- Indeterminate outcomes never grant sensitive privileges.
- Audit logs provide sufficient investigative detail without containing secrets.
- Recovery plans exist when verifiers or reference value services are unavailable.

## 17. Operations checklist

- [ ] VM root of trust and trust boundaries are defined.
- [ ] Secure Boot, measured boot, and attestation are clearly distinguished.
- [ ] TPM/vTPM or appropriate attestation mechanisms are enabled and verified.
- [ ] Platform-appropriate PCR profiles and hash algorithms are selected.
- [ ] Event logs are collected and replayability is verified.
- [ ] Quotes carry valid signatures and bind to fresh nonces.
- [ ] Certificate chains for Attestation Keys or reports are verified.
- [ ] Reference values have provenance, versions, and approvers.
- [ ] Policy explicitly handles pass, fail, and indeterminate states.
- [ ] Boot measurements are distinguished from runtime integrity.
- [ ] Confidential VMs validate TCB and reports under the proper trust model.
- [ ] Secret tokens carry scoped subjects, audiences, and short expirations.
- [ ] Relying parties validate tokens before granting privileges.
- [ ] Processes exist for baseline updates, revocations, and rollbacks.
- [ ] Failure rates, latency, certificates, and verifier health are monitored.
- [ ] Scenarios tested for replay, corrupted logs, firmware drift, and verifier outages.
- [ ] Procedures exist to quarantine or reimage non-compliant machines.
- [ ] Audit logs contain no private keys, secrets, or full tokens.

## Conclusion

Measured boot records boot-component state via cryptographic measurements in PCRs; event logs supply context to interpret those measurements; TPM quotes let verifiers check state and freshness. Remote attestation combines that evidence with reference values and policy to decide whether a VM may receive secrets or join sensitive workloads. Secure Boot blocks untrusted boot components, while confidential computing adds hardware memory protections and dedicated evidence. When deploying, manage baselines with clear provenance, distinguish boot from runtime, handle indeterminate states explicitly, and integrate attestation with workload identity, least privilege, and operational monitoring.
